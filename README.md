# Mantis to Bitbucket Issues

A simple Python script that generates an importable zip archive from mantis issues export.

# How to use
* Install the dependencies:
```pip install -r requirements```
* Run the script by specifying the required parameters.

# Input file formats
## Bug attachments file
```
    [
	{
		"bug_id" : 8,
		"filename" : "config.log"
	},
	{
		"bug_id" : 17,
		"filename" : "screenshots.zip"
	}
	]
```

Such file can be retrieved by executing the following SQL command against the Mantis database:
```
SELECT bug_id, filename FROM mantis_bug_file_table;
```

## Reporters mapping file
```
    [ { "mantis_user": "bitbucket_user" } ]
```