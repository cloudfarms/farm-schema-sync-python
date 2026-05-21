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

By default, the database file is called `farmSync.db`. It is possible to rename the file by adding a command line argument with the name of the file.

## Setup

Download the source code.

It is RECOMMENDED to create a virtual environment before installation as it allows for easier uninstallation:

## Virtual environment

It is possible to specify python version in all OS by appending the version after python. Ex: `python3.9`

***Windows***

Powershell
```bash
python -m venv .venv
.venv/scripts/Activate.ps1
```

Command Prompt
```bash
python -m venv .venv
.venv/scripts/activate.bat
```

***Linux/macOs***
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## App installation

You can install the app using the following command:
```bash
pip install .
```
or:
```bash
python -m pip install .
```

Afterwards, run the app with the command:
```bash
farmSync
```

> Global installation vs Virtual environment
>
> If the app is installed globally, it should be possible to run the command from any directory
>
> If the app is installed in a virtual environment, the command will only be available in the app directory
