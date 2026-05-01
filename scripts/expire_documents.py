#!/usr/bin/env python3
"""Delete documents past their 14-day expiry to free storage.
Run daily via cron: 0 3 * * * /opt/wescan/venv/bin/python /opt/wescan/scripts/expire_documents.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app, db
from app.models import Document, SignedDocument
from datetime import datetime

app = create_app()
with app.app_context():
    cutoff = datetime.utcnow()
    expired = Document.query.filter(Document.expires_at < cutoff).all()

    if not expired:
        print('No expired documents to clean up.')
        sys.exit(0)

    doc_ids = [d.id for d in expired]

    # Delete associated signed documents first (FK constraint)
    signed_count = SignedDocument.query.filter(
        SignedDocument.document_id.in_(doc_ids)
    ).delete(synchronize_session='fetch')

    # Count stats before delete
    pending = sum(1 for d in expired if d.status == 'pending')
    signed = len(expired) - pending
    total_mb = sum(d.file_size for d in expired) / (1024 * 1024)

    for d in expired:
        db.session.delete(d)

    db.session.commit()

    print(f'Deleted {len(expired)} expired documents '
          f'({total_mb:.1f} MB freed, {signed} signed, {pending} pending, '
          f'{signed_count} signeddoc rows removed).')
