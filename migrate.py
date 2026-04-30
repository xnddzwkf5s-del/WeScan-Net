"""Database migration management with Flask-Migrate (Alembic).

Usage:
    flask db init          # One-time: creates migrations/ dir
    flask db migrate -m "description"   # Auto-generate migration
    flask db upgrade       # Apply pending migrations
    flask db downgrade     # Rollback last migration
"""
from flask_migrate import Migrate
from app import create_app, db

app = create_app()
migrate = Migrate(app, db)

if __name__ == '__main__':
    app.run()
