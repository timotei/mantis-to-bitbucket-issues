##############################################################################
# Mantis to Bitbucket issues converter
#
# Copyright (C) 2015 Timotei Dolean <timotei21@gmail.com>
# and contributing authors (see AUTHORS file)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################
from __future__ import print_function
from argparse import ArgumentParser
from collections import defaultdict
import json
import os
import errno
import shutil
import tempfile
from datetime import datetime
import zipfile
from bs4 import BeautifulSoup


class IssuesConverter:
    def __init__(self, args):
        self.args = args
        self.users = self.createUserMappings()

    def transformUser(self, mantisUser):
        mantisReporterLowercase = mantisUser.lower()
        if mantisReporterLowercase in self.users:
            return self.users[mantisReporterLowercase]

        return self.args.default_user

    def createUserMappings(self):
        users = {}
        usersJson = self.getJsonObjectFromFile(self.args.user_mapping_file)

        for key in usersJson:
            pair = key.items()[0]
            users[pair[0].lower()] = pair[1]

        return users

    @staticmethod
    def getJsonObjectFromFile(path):
        with open(path) as jsonFile:
            jsonData = jsonFile.read()
            return json.loads(jsonData)

    @staticmethod
    def transformMantisSeverity(mantisSeverity):
        priorities = {
            "feature": "trivial",
            "trivial": "trivial",
            "text": "trivial",
            "tweak": "trivial",
            "minor": "minor",
            "major": "major",
            "crash": "critical",
            "block": "blocker"
        }

        return priorities[mantisSeverity]

    @staticmethod
    def transformStatus(mantisStatus):
        statuses = {
            "new": "new",
            "feedback": "on hold",
            "acknowledged": "open",
            "confirmed": "open",
            "assigned": "open",
            "resolved": "resolved",
            "closed": "resolved",
        }
        return statuses[mantisStatus]

    @staticmethod
    def severityToKind(severity):
        if severity == 'feature' or severity == 'text':
            return 'task'

        if severity == 'tweak':
            return 'enhancement'

        return 'bug'

    @staticmethod
    def transformDate(mantisDate):
        return datetime.fromtimestamp(float(mantisDate)).isoformat()

    @staticmethod
    def stringOf(xmlNode):
        return xmlNode.string if xmlNode else ""

    @staticmethod
    def initialiseAttachmentsOutputDir(attachmentsOutputPath):
        try:
            os.makedirs(attachmentsOutputPath)
        except OSError as ex:
            if ex.errno != errno.EEXIST:
                raise

    def convert(self):
        tempPath = tempfile.mkdtemp()
        attachmentsOutputPath = os.path.join(tempPath, 'attachments')
        self.initialiseAttachmentsOutputDir(attachmentsOutputPath)
        dbJsonFileName = 'db-1.0.json'
        outputJsonPath = os.path.join(tempPath, dbJsonFileName)
        if self.args.verbose:
            print("Starting conversion using output path: %s ... " % tempPath)

        bugAttachmentMappings = defaultdict(list)

        if self.args.bug_attachments_file:
            jsonObject = self.getJsonObjectFromFile(self.args.bug_attachments_file)
            for bugJson in jsonObject:
                bugAttachmentMappings[str(bugJson['bug_id'])].append(bugJson['diskfile'])

        with open(self.args.input_xml) as inputXmlFile:
            with open(outputJsonPath, mode='w+') as outputJsonFile:
                mantisRootNode = BeautifulSoup(inputXmlFile)

                db = defaultdict(list, {"meta": {"default_kind": "bug"}})
                issueIds = self.processXml(db, mantisRootNode, attachmentsOutputPath, bugAttachmentMappings)
                if self.args.bug_notes_file:
                    bugsJson = self.getJsonObjectFromFile(self.args.bug_notes_file)
                    self.processBugNotes(db, issueIds, bugsJson)

                outputJsonFile.write(json.dumps(db, indent=4, sort_keys=True))

        with zipfile.ZipFile(self.args.output_zip, mode='w', compression=zipfile.ZIP_DEFLATED) as zipFile:
            zipFile.write(outputJsonPath, dbJsonFileName)
            for root, dirs, files in os.walk(attachmentsOutputPath):
                for file in files:
                    zipFile.write(os.path.join(root, file), os.path.join('attachments', file))

    def processXml(self, db, mantisNode, attachmentsOutputPath, bugAttachmentMappings):
        versions = set()
        milestones = set()
        components = set()
        issueIds = set()
        unresolvedReporters = set()

        for issueNode in mantisNode.find_all('issue'):
            version = self.stringOf(issueNode.version)
            milestone = self.stringOf(issueNode.target_version)
            component = self.stringOf(issueNode.category)
            mantisReporter = issueNode.reporter.string
            reporter = self.transformUser(mantisReporter)
            handler = self.transformUser(self.stringOf(issueNode.handler))
            issueContent = self.stringOf(issueNode.description)
            issueId = issueNode.id.string
            kind = self.severityToKind(issueNode.severity.string)

            if self.args.verbose:
                print("Processing issue %s ..." % issueId)

            issueContent += '\n\n**Reproducibility:** %s' % issueNode.reproducibility.string
            if issueNode.steps_to_reproduce:
                issueContent += '\n\n**Steps to reproduce:** %s' % self.stringOf(issueNode.steps_to_reproduce)
            if issueNode.additional_information:
                issueContent += '\n\n**Additional information:** %s' % self.stringOf(issueNode.additional_information)
            if issueNode.os:
                issueContent += '\n\n**OS:** %s, **OS build:** %s, **Platform:** %s' % \
                                (self.stringOf(issueNode.os), self.stringOf(issueNode.os_build),
                                 self.stringOf(issueNode.platform))

            if reporter == self.args.default_user:
                issueContent = '**Automatic migration. Original reporter: "%s"**\n\n%s' % (mantisReporter, issueContent)
                unresolvedReporters.add(mantisReporter)

            issue = {
                'id': issueId,
                'reporter': reporter,
                'assignee': handler,
                'priority': self.transformMantisSeverity(issueNode.severity.string),
                'status': self.transformStatus(issueNode.status.string),
                'component': component,
                'created_on': self.transformDate(issueNode.date_submitted.string),
                'updated_on': self.transformDate(issueNode.last_updated.string),
                'content_updated_on': self.transformDate(issueNode.last_updated.string),
                'version': version,
                'milestone': milestone,
                'title': issueNode.summary.string,
                'content': issueContent,

                # BB required
                'kind': kind
            }

            issueIds.add(issueId)

            if parsedArgs.attachments_directory and bugAttachmentMappings.has_key(issueId):
                if self.args.verbose:
                    print("Processing attachments for %s ..." % issueId)

                for filename in bugAttachmentMappings[issueId]:
                    sourceFile = os.path.join(parsedArgs.attachments_directory, filename)
                    targetFile = os.path.join(attachmentsOutputPath, filename)

                    if not os.path.exists(sourceFile):
                        print("*WARNING* Attachment file %s for bug %s does not exist" % (sourceFile, issueId))
                        continue
                    shutil.copyfile(sourceFile, targetFile)

                    db['attachments'].append({
                        'filename': filename,
                        'issue': issueId,
                        'path': 'attachments/%s' % filename
                    })

            if version:
                versions.add(version)
            if milestone:
                milestones.add(milestone)
            if component:
                components.add(component)
            db['issues'].append(issue)

        db['versions'] = [{"name": v} for v in versions]
        db['milestones'] = [{"name": m} for m in milestones]
        db['components'] = [{"name": c} for c in components]

        print("*WARNING* The following reporters were not resolved: \n%s"
              % '\n'.join(r for r in sorted(unresolvedReporters)))

        return issueIds

    def processBugNotes(self, db, issueIds, bugNotes):
        if self.args.verbose:
            print("Processing bug notes ...")

        for bugNote in bugNotes:
            bugId = bugNote['bug_id']
            if str(bugId) not in issueIds:
                continue

            mantisUsername = bugNote['username']
            resolvedReporter = self.transformUser(mantisUsername)
            noteText = bugNote['note']

            if resolvedReporter == self.args.default_user:
                noteText = '**Original reporter: %s**\n\n%s' % (mantisUsername, noteText)

            comment = {
                'content': noteText,
                'created_on': self.transformDate(bugNote['date_submitted']),
                'updated_on': self.transformDate(bugNote['last_modified']),
                'id': bugNote['bugnote_text_id'],
                'user': resolvedReporter,
                'issue': bugId,
            }
            db['comments'].append(comment)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('input_xml', help='Input file in XML format with the exported issues.')
    parser.add_argument('output_zip', help='Path where to generate the zip to be imported into Bitbucket.')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--attachments-directory', help='Folder that contains the exported attachments.')
    parser.add_argument('--default-user', help='Default user for unresolved users.', default='')
    parser.add_argument('--bug-attachments-file',
                        help='A JSON file with an array containing "bug_id":"filename" mappings.')
    parser.add_argument('--user-mapping-file',
                        help='A JSON file with an array containing "mantis_user_id":"bitbucket_user_id" mappings.')
    parser.add_argument('--bug-notes-file',
                        help='A JSON file containing the bug notes details.')

    parsedArgs = parser.parse_args()

    if not parsedArgs.attachments_directory or not parsedArgs.bug_attachments_file:
        print("*WARNING* No attachments directory or bug attachments file specified, will skip attachments processing.")

    if not parsedArgs.bug_notes_file:
        print("*WARNING* No bug-notes file specified, will skip bug notes processing.")

    converter = IssuesConverter(parsedArgs)
    converter.convert()