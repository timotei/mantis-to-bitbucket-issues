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
        self.reporters = self.createReporterMappings()

    def transformReporter(self, mantisReporter):
        if mantisReporter in self.reporters:
            return self.reporters[mantisReporter]

        return self.args.default_reporter

    def createReporterMappings(self):
        reporters = {}
        reportersJson = self.getJsonObjectFromFile(self.args.reporter_mapping_file)

        for key in reportersJson:
            pair = key.items()[0]
            reporters[pair[0]] = pair[1]

        return reporters

    @staticmethod
    def getJsonObjectFromFile(path):
        with open(path) as jsonFile:
            jsonData = jsonFile.read()
            return json.loads(jsonData)

    @staticmethod
    def transformPriority(mantisPriority):
        # TODO: use severity?
        priorities = {
            "none": "trivial",
            "low": "minor",
            "normal": "major",
            "high": "critical",
            "urgent": "critical",
            "immediate": "blocker"
        }

        return priorities[mantisPriority]

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
                bugAttachmentMappings[str(bugJson['bug_id'])].append(bugJson['filename'])

        with open(self.args.input_xml) as inputXmlFile:
            with open(outputJsonPath, mode='w+') as outputJsonFile:
                mantisRootNode = BeautifulSoup(inputXmlFile)
                db = self.processXml(mantisRootNode, attachmentsOutputPath, bugAttachmentMappings)
                outputJsonFile.write(json.dumps(db, indent=4, sort_keys=True))

        with zipfile.ZipFile(self.args.output_zip, mode='w', compression=zipfile.ZIP_DEFLATED) as zipFile:
            zipFile.write(outputJsonPath, dbJsonFileName)
            for root, dirs, files in os.walk(attachmentsOutputPath):
                for file in files:
                    zipFile.write(os.path.join(root, file), os.path.join('attachments', file))

    def processXml(self, mantisNode, attachmentsOutputPath, bugAttachmentMappings):
        db = defaultdict(list, {"meta": {"default_kind": "bug"}})

        versions = set()
        components = set()
        for issueNode in mantisNode.find_all('issue'):
            version = self.stringOf(issueNode.version)
            component = self.stringOf(issueNode.category)
            reporter = self.transformReporter(issueNode.reporter.string)
            issueContent = self.stringOf(issueNode.description)
            issueId = issueNode.id.string

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

            if reporter == self.args.default_reporter:
                issueContent = '**Automatic migration. Original reporter: "%s"**\n\n%s' % (
                    issueNode.reporter.string, issueContent)

            issue = {
                'id': issueId,
                'reporter': reporter,
                'priority': self.transformPriority(issueNode.priority.string),
                'status': self.transformStatus(issueNode.status.string),
                'category': component,
                'created_on': self.transformDate(issueNode.date_submitted.string),
                'updated_on': self.transformDate(issueNode.last_updated.string),
                'content_updated_on': self.transformDate(issueNode.last_updated.string),
                'version': version,
                'title': issueNode.summary.string,
                'content': issueContent,

                # BB required
                'kind': 'bug'
            }

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
            if component:
                components.add(component)
            db['issues'].append(issue)

        db['versions'] = [{"name": v} for v in versions]
        db['components'] = [{"name": c} for c in components]
        return db

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('input_xml', help='Input file in XML format with the exported issues.')
    parser.add_argument('output_zip', help='Path where to generate the zip to be imported into Bitbucket.')
    parser.add_argument('--verbose')
    parser.add_argument('--attachments-directory', help='Folder that contains the exported attachments.')
    parser.add_argument('--default-reporter', help='Default reporter user for unresolved users.', default='')
    parser.add_argument('--bug-attachments-file',
                        help='A JSON file with an array containing "bug_id":"filename" mappings.')
    parser.add_argument('--reporter-mapping-file',
                        help='A JSON file with an array containing "mantis_user_id":"bitbucket_user_id" mappings.')

    parsedArgs = parser.parse_args()

    if not parsedArgs.attachments_directory or not parsedArgs.bug_attachments_file:
        print("*WARNING* No attachments directory or bug attachments file specified, will skip attachments processing.")

    converter = IssuesConverter(parsedArgs)
    converter.convert()