import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Resource, User

INVENTORY_RESOURCES = [
    {"type": "bed", "name": "Bed", "total_quantity": 7},
    {"type": "gameready_feet", "name": "Gameready for feet", "total_quantity": 3},
    {"type": "gameready_thighs", "name": "Gameready for thighs", "total_quantity": 4},
    {
        "type": "compression_lower_body",
        "name": "Compression boots for lower body",
        "total_quantity": 1,
    },
    {"type": "heat", "name": "Heat packs", "total_quantity": 10},
    {"type": "cold", "name": "Ice packs", "total_quantity": 10},
    {"type": "ice_bath", "name": "Ice bathtubs", "total_quantity": 3},
]


def seed_inventory():
    result = []

    for resource in INVENTORY_RESOURCES:
        existing = Resource.query.filter_by(type=resource["type"]).first()
        if existing is None:
            new_resource = Resource(
                type=resource["type"],
                name=resource["name"],
                total_quantity=resource["total_quantity"],
            )
            db.session.add(new_resource)
            result.append(new_resource)

    return result


@click.command("seed-inventory")
@with_appcontext
def seed_inventory_command():
    try:
        resources_result = seed_inventory()
        db.session.commit()
        for resource in resources_result:
            click.echo(f"{resource.type}, {resource.name}, {resource.total_quantity}")
        if not resources_result:
            click.echo("Inventory already seeded: nothing to create.")
    except SQLAlchemyError as error:
        db.session.rollback()
        raise click.ClickException(f"seed-inventory failed:\n {error}")


DEV_PASSWORD = "dev_password_123"

DEV_USERS = [
    {"role": "physio", "name": "Test_physio1", "email": "test_physio1@example.com"},
    {"role": "physio", "name": "Test_physio2", "email": "test_physio2@example.com"},
    {"role": "client", "name": "Test_client1", "email": "test_client1@example.com"},
    {"role": "client", "name": "Test_client2", "email": "test_client2@example.com"},
    {"role": "client", "name": "Test_client3", "email": "test_client3@example.com"},
    {"role": "client", "name": "Test_client4", "email": "test_client4@example.com"},
]


def seed_dev_users():
    result = []
    password_hash = None

    for user in DEV_USERS:
        email = user["email"].strip().lower()
        existing = User.query.filter_by(email=email).first()

        if existing is None:
            if password_hash is None:
                password_hash = generate_password_hash(DEV_PASSWORD)
            new_user = User(
                role=user["role"],
                name=user["name"],
                email=email,
                password_hash=password_hash,
            )
            db.session.add(new_user)
            result.append(new_user)

    return result


@click.command("seed-dev-users")
@with_appcontext
def seed_dev_users_command():
    if not current_app.config.get("ENABLE_DEV_SEED"):
        raise click.ClickException(
            "seed-dev-users is disabled. "
            "Set ENABLE_DEV_SEED=1 in .env to enable it (development only)."
        )
    try:
        users_results = seed_dev_users()
        db.session.commit()
        for user in users_results:
            click.echo(f"{user.role}, {user.name}, {user.email}")
        if not users_results:
            click.echo("Users already seeded: nothing to create")
    except SQLAlchemyError as error:
        db.session.rollback()
        raise click.ClickException(f"seed-dev-users failed:\n {error}")
