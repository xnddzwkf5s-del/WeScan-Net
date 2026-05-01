"""PDF editing tools — merge, split, rotate, delete pages. No login required."""
import os
import io
import uuid
import fitz
from flask import Blueprint, request, jsonify, send_file
from datetime import datetime

pdf_edit = Blueprint('pdf_edit', __name__)

TEMP_DIR = '/tmp/wescan-edit'

# ── Helpers ─────────────────────────────────────────────────────────────────

def _ensure_temp():
    os.makedirs(TEMP_DIR, exist_ok=True)


def _session_dir(session_id):
    d = os.path.join(TEMP_DIR, session_id)
    os.makedirs(d, exist_ok=True)
    return d


def _cleanup_session(session_id):
    import shutil
    d = os.path.join(TEMP_DIR, session_id)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


# ── Upload ──────────────────────────────────────────────────────────────────

@pdf_edit.route('/api/pdf-edit/upload', methods=['POST'])
def upload():
    _ensure_temp()
    session_id = uuid.uuid4().hex
    savedir = _session_dir(session_id)

    files_info = []
    for key in sorted(request.files.keys()):
        f = request.files[key]
        if not f.filename:
            continue
        raw = f.read()
        if not raw:
            continue

        try:
            doc = fitz.open(stream=raw, filetype='pdf')
            page_count = doc.page_count
            doc.close()
        except Exception:
            return jsonify({'error': f'{f.filename} is not a valid PDF'}), 400

        if page_count == 0:
            return jsonify({'error': f'{f.filename} has no pages'}), 400

        file_id = uuid.uuid4().hex[:8]
        filepath = os.path.join(savedir, f'{file_id}.pdf')
        with open(filepath, 'wb') as fh:
            fh.write(raw)

        files_info.append({
            'id': file_id,
            'name': f.filename,
            'pages': page_count
        })

    if not files_info:
        return jsonify({'error': 'No valid PDFs uploaded'}), 400

    return jsonify({
        'session_id': session_id,
        'files': files_info
    })


# ── Process ─────────────────────────────────────────────────────────────────

@pdf_edit.route('/api/pdf-edit/process', methods=['POST'])
def process():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    action = data.get('action', '')
    params = data.get('params', {})

    if not session_id or not action:
        return jsonify({'error': 'Missing session_id or action'}), 400

    savedir = _session_dir(session_id)
    if not os.path.isdir(savedir):
        return jsonify({'error': 'Session expired. Re-upload your files.'}), 404

    file_ids = params.get('file_ids', [])
    if not file_ids:
        return jsonify({'error': 'No files specified'}), 400

    if action == 'merge':
        return _merge(session_id, savedir, file_ids, params)
    elif action == 'split':
        return _split(session_id, savedir, file_ids, params)
    else:
        return jsonify({'error': f'Unknown action: {action}'}), 400


def _merge(session_id, savedir, file_ids, params):
    """Merge PDFs — optionally delete and rotate pages."""
    delete_map = params.get('delete_pages', {})
    rotate_map = params.get('rotate_pages', {})

    merged = fitz.open()

    for fid in file_ids:
        path = os.path.join(savedir, f'{fid}.pdf')
        if not os.path.isfile(path):
            return jsonify({'error': f'File not found: {fid}'}), 404

        doc = fitz.open(path)
        total = doc.page_count

        to_delete = set()
        for pn in delete_map.get(fid, []):
            to_delete.add(int(pn))

        rotates = {}
        for r in rotate_map.get(fid, []):
            page_num = int(r.get('page', 0)) - 1
            angle = int(r.get('angle', 0))
            if 0 <= page_num < total and angle in (90, 180, 270):
                rotates[page_num] = angle

        for i in range(total):
            if (i + 1) in to_delete:
                continue
            page = doc[i]
            if i in rotates:
                page.set_rotation(rotates[i])
            merged.insert_pdf(doc, from_page=i, to_page=i)

        doc.close()

    if merged.page_count == 0:
        merged.close()
        return jsonify({'error': 'All pages were deleted. Nothing to output.'}), 400

    output = io.BytesIO()
    merged.save(output, garbage=4, deflate=True)
    merged.close()
    output.seek(0)

    now = datetime.utcnow()
    filename = f'wescan-net-{now.strftime("%d%b%y")}.pdf'

    _cleanup_session(session_id)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


def _split(session_id, savedir, file_ids, params):
    """Split pages from a single PDF into a new PDF."""
    pages_to_extract = params.get('pages', [])
    if not pages_to_extract:
        return jsonify({'error': 'No pages specified for split'}), 400

    fid = file_ids[0]
    path = os.path.join(savedir, f'{fid}.pdf')
    if not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404

    doc = fitz.open(path)
    total = doc.page_count
    out = fitz.open()

    for pn in pages_to_extract:
        pn = int(pn)
        if pn < 1 or pn > total:
            doc.close()
            out.close()
            return jsonify({'error': f'Page {pn} does not exist (1-{total})'}), 400
        out.insert_pdf(doc, from_page=pn - 1, to_page=pn - 1)

    doc.close()

    if out.page_count == 0:
        out.close()
        return jsonify({'error': 'No pages selected'}), 400

    output = io.BytesIO()
    out.save(output, garbage=4, deflate=True)
    out.close()
    output.seek(0)

    now = datetime.utcnow()
    filename = f'wescan-net-{now.strftime("%d%b%y")}.pdf'

    _cleanup_session(session_id)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
