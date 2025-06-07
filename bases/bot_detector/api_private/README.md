# public-api
structure:
- src: contains all program files
- src.api: contains the api
- src.app: contains the database logic
- src.core: contains the core componetns
- src.core.database: contains all the database functionality

# setup
## windows
creating a python venv to work in and install the project requirements
```sh
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
## linux
make sure to have pip
```sh
sudo apt update -y && sudo apt upgrade -y
sudo apt install python3.10-venv -y
sudo apt install python3-pip -y
```
```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```
# for admin purposes saving & upgrading
when you added some dependancies update the requirements
```sh
.venv\Scripts\activate
call pip freeze > requirements.txt
```
when you want to upgrade the dependancies
```sh
.venv\Scripts\activate
powershell "(Get-Content requirements.txt) | ForEach-Object { $_ -replace '==', '>=' } | Set-Content requirements.txt"
call pip install -r requirements.txt --upgrade
call pip freeze > requirements.txt
powershell "(Get-Content requirements.txt) | ForEach-Object { $_ -replace '>=', '==' } | Set-Content requirements.txt"
```