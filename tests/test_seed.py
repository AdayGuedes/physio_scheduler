import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Resource
from app.seed import seed_inventory, seed_inventory_command


def test_seed_inventory_creates_all_resources(app):
    seed_inventory()
    db.session.commit()

    resources = Resource.query.all()

    assert len(resources) == 7
    assert {resource.type for resource in resources} == set(Resource.type.type.enums)


def test_seed_inventory_is_idempotent(app):
    seed_inventory()
    db.session.commit()
    seed_inventory()
    db.session.commit()

    resources = Resource.query.all()

    assert len(resources) == 7
    assert len({resource.type for resource in resources}) == 7


def test_seed_inventory_keeps_existing_resource(app):
    db.session.add(Resource(type="heat", name="Heat pack", total_quantity=2))
    db.session.commit()

    created = seed_inventory()
    db.session.commit()

    heat = Resource.query.filter_by(type="heat").one()

    assert heat.name == "Heat pack"
    assert heat.total_quantity == 2
    assert len(created) == 6
    assert Resource.query.count() == 7


def test_seed_inventory_command_seeds_database(app):
    result = app.test_cli_runner().invoke(seed_inventory_command)

    assert result.exit_code == 0
    assert len(result.output.strip().splitlines()) == 7
    assert "bed, Bed, 7" in result.output

    db.session.rollback()

    assert Resource.query.count() == 7


def test_seed_inventory_command_skips_existing_inventory(app):
    runner = app.test_cli_runner()
    runner.invoke(seed_inventory_command)

    result = runner.invoke(seed_inventory_command)

    assert result.exit_code == 0
    assert "Inventory already seeded" in result.output

    db.session.rollback()

    assert Resource.query.count() == 7


def test_seed_inventory_command_fails_on_integrity_error(app):
    db.session.add(Resource(type="ice_bath", name="Bed", total_quantity=3))
    db.session.commit()

    result = app.test_cli_runner().invoke(seed_inventory_command)

    assert result.exit_code == 1
    assert "seed-inventory failed" in result.output
    assert Resource.query.count() == 1


def test_seed_inventory_raises_on_duplicate_name(app):
    db.session.add(Resource(type="ice_bath", name="Bed", total_quantity=3))
    db.session.commit()

    with pytest.raises(IntegrityError):
        seed_inventory()
        db.session.commit()

    db.session.rollback()
