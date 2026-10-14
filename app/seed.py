import click
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Resource

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
