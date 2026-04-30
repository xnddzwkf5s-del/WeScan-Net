#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

# Ensure data directory exists
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)

load_dotenv()

from app import create_app
from app.auth import init_oauth

app = create_app()
init_oauth(app)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
