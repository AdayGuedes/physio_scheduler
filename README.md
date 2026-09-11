# physio_scheduler

After setting up the project and before starting working, take a look and take in considerstion the best_practices file. This will show you how the names for branches, PRs, and commits must be

## Python version
- The python version has to be 3.11+

## Setup project
- Follow this steps to set it up:
``` bash
git clone git@github.com:AdayGuedes/physio_scheduler.git
cd physio_scheduler
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configure env
- This will allow you to use the app:
First create .env  
copy the two lines that are in .env.example
paste it in .env
In the root of the project then do:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Whatever is comming out of the second script, paste it in SECRET_KEY in the .env file, NOT IN THE .env.example
DATABASE_URL remains the same

## Database
The Database is still in progress but in the future, you will have to do some scripts that will be here

## Run the app
- The script is:
```bash
python run.py
```