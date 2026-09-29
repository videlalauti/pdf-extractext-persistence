"""Tests de la construcción de la URL de Mongo a partir de la configuración por env."""

from persistence.mongodb_connection import MongoSettings


def test_build_url_uses_the_six_settings():
    settings = MongoSettings(
        mongodb_root_username="admin",
        mongodb_root_password="changeme",
        mongodb_host="mongo",
        mongodb_port="27017",
        mongodb_database_name="pdf_extractext",
        mongodb_auth_source="admin",
    )

    assert (
        settings.build_url()
        == "mongodb://admin:changeme@mongo:27017/pdf_extractext?authSource=admin"
    )


def test_build_url_percent_encodes_credentials():
    """Una credencial con @ o / cortaría la URL si fuera sin encodear."""
    settings = MongoSettings(
        mongodb_root_username="user@example.com",
        mongodb_root_password="p@ss:w/rd#1",
    )

    url = settings.build_url()

    assert "user%40example.com" in url
    assert "p%40ss%3Aw%2Frd%231" in url
    assert "mongodb://user%40example.com:p%40ss%3Aw%2Frd%231@" in url
