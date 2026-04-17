## Cloudfarms database replication demo

This is a demo application showing an approach to replicate
the Cloudfarms data to a local database.

The Cloudfarms API provides a method do read data changes
(upserts and deletes) and to store them in a local database.

This demo is implemented in Python and stores the data in a local database.

## Usage

Set up the environment variables or provide the `.env` file
with the following entries:

```properties
CF_BASE_URL="https://pigs.cloudfarms.com"
CF_CLIENT_ID="your client id"
CF_CLIENT_SECRET="your client secret"
```

The application will create all the needed tables and load the data from Cloudfarms. 
If the database already exits, the application load just the data changed since the last download.

