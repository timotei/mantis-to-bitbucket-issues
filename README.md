# Mantis to Bitbucket Issues

A simple Python script that generates an importable zip archive from mantis issues export.

# How to use
* Install the dependencies:
```pip install -r requirements```
* Run the script by specifying the required parameters.

# Input file formats
## Bug attachments file
The format of the file is:
```
    [
	{
		"bug_id" : 8,
		"diskfile" : "config.log"
	},
	{
		"bug_id" : 17,
		"diskfile" : "screenshots.zip"
	}
	]
```

Such file can be retrieved by executing the following SQL command against the Mantis database:
```
SELECT bug_id, diskfile FROM mantis_bug_file_table WHERE filename <> '';
```

## Reporters mapping file
The format of the file is:
```
    [ { "mantis_user": "bitbucket_user" } ]
```

## Bugnotes file
The format of the file is:
```
[
    {
        "bug_id": 3,
        "bugnote_text_id": 1,
        "date_submitted": 1129152778,
        "last_modified": 1129152778,
        "note": "bug note",
        "username": "mantis_user"
    },
    {
        "bug_id": 14,
        "bugnote_text_id": 3,
        "date_submitted": 1130970133,
        "last_modified": 1130970133,
        "note": "bug note",
        "username": "mantis_user"
    }
]
```

Such file can be retrieved by executing the following SQL command against the Mantis database:
```
SELECT bug_id, bugnote_text_id, note, username, date_submitted, last_modified FROM mantis_bugnote_text_table mbtt JOIN mantis_bugnote_table mbt ON (mbtt.id=mbt.bugnote_text_id) JOIN mantis_user_table mut ON (mbt.reporter_id = mut.id)
```