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
copy the lines that are in .env.example
paste it in .env
In the root of the project then do:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Whatever is coming out of the script above, paste it in SECRET_KEY in the .env file, NOT IN THE .env.example

- `SECRET_KEY`: the generated value
- `DATABASE_URL`: remains the same
- `ENABLE_DEV_SEED`: stays empty unless you need the development users described in "Seed data"

## Database
The Database is still in progress but in the future, you will have to do some scripts that will be here

## Seed data
- Initial inventory:
```bash
flask seed-inventory
```

- Development users (2 physios and 4 clients). The command refuses to run unless
  `ENABLE_DEV_SEED=1` is set in `.env` and Flask runs in debug mode. The users share a
  known password, so never set the flag in production or against a shared database:
```bash
flask --debug seed-dev-users
```

Running either command again skips what already exists.

## Run the app
- The script is:
```bash
python run.py
```