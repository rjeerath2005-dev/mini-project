from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS
import json
import os
from datetime import datetime
import uuid
import time


app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
PAGES_DIR = os.path.join(FRONTEND_DIR, 'pages')
STATIC_DIR = FRONTEND_DIR
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def next_id(data):
    return max((item.get('id', 0) for item in data), default=0) + 1


def ensure_data_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    defaults = {
        'expenses.json': [],
        'income.json': [],
        'rentals.json': [],
        'tractors.json': [
            {"id": 1, "name": "Tractor A", "rate_per_day": 1000, "status": "Available"},
            {"id": 2, "name": "Tractor B", "rate_per_day": 1200, "status": "Available"}
        ],
        'schemes.json': [
            {"id": 1, "name": "PM-KISAN", "full_name": "Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)", "category": "Income Support", "type": "Direct Benefit", "ministry": "Ministry of Agriculture", "benefit": "₹6000 per year", "eligibility": "Small and marginal farmers", "documents": ["Aadhaar", "Land records"], "apply_link": "https://pmkisan.gov.in", "description": "Income support for small and marginal farmers."},
            {"id": 2, "name": "PMFBY", "full_name": "Pradhan Mantri Fasal Bima Yojana", "category": "Insurance", "type": "Crop Insurance", "ministry": "Ministry of Agriculture", "benefit": "Crop insurance coverage", "eligibility": "All eligible farmers", "documents": ["Aadhaar", "Land records", "Bank details"], "apply_link": "https://pmfby.gov.in", "description": "Crop insurance scheme."}
        ],
        'farmers.json': [],
        'admin.json': {"username": "admin", "password": "admin123"},
        'tokens.json': []
    }
    for fn, content in defaults.items():
        path = os.path.join(DATA_DIR, fn)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)


ensure_data_files()


def load_tokens():
    try:
        return read_json('tokens.json')
    except Exception:
        return []


def save_tokens(tokens):
    write_json('tokens.json', tokens)


def create_token(username, ttl=3600):
    tokens = load_tokens()
    token = str(uuid.uuid4())
    expires = int(time.time()) + ttl
    tokens.append({'token': token, 'user': username, 'expires': expires})
    save_tokens(tokens)
    return token


def verify_token(token):
    tokens = load_tokens()
    now = int(time.time())
    for t in tokens:
        if t.get('token') == token and t.get('expires', 0) >= now:
            return True
    return False


def revoke_token(token):
    tokens = load_tokens()
    tokens = [t for t in tokens if t.get('token') != token]
    save_tokens(tokens)


def check_admin_credentials(username, password):
    try:
        admin = read_json('admin.json')
    except Exception:
        return False
    return username == admin.get('username') and password == admin.get('password')


def require_admin(fn):
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
            if verify_token(token):
                return fn(*args, **kwargs)
        return jsonify({'error': 'Unauthorized'}), 401
    wrapper.__name__ = fn.__name__
    return wrapper


# Frontend routes
@app.route('/', methods=['GET'])
def serve_index():
    return send_from_directory(PAGES_DIR, 'index.html')


@app.route('/pages/<path:filename>', methods=['GET'])
def serve_page(filename):
    return send_from_directory(PAGES_DIR, filename)


@app.route('/static/<path:filename>', methods=['GET'])
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route('/<path:subpath>', methods=['GET'])
def serve_any(subpath):
    if subpath.startswith('api/'):
        abort(404)
    candidate = os.path.join(PAGES_DIR, subpath)
    if os.path.isfile(candidate):
        return send_from_directory(PAGES_DIR, subpath)
    if not subpath.endswith('.html'):
        candidate_html = os.path.join(PAGES_DIR, subpath + '.html')
        if os.path.isfile(candidate_html):
            return send_from_directory(PAGES_DIR, subpath + '.html')
    candidate_static = os.path.join(STATIC_DIR, subpath)
    if os.path.isfile(candidate_static):
        return send_from_directory(STATIC_DIR, subpath)
    abort(404)


# Admin
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    body = request.json or {}
    username = body.get('username')
    password = body.get('password')
    if not username or not password:
        return jsonify({'error': 'Missing credentials'}), 400
    if check_admin_credentials(username, password):
        token = create_token(username)
        return jsonify({'token': token})
    return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1]
        revoke_token(token)
    return jsonify({'ok': True})


@app.route('/api/admin/schemes', methods=['POST'])
@require_admin
def admin_create_scheme():
    data = read_json('schemes.json')
    body = request.json or {}
    body['id'] = next_id(data)
    body['documents'] = body.get('documents') or []
    data.append(body)
    write_json('schemes.json', data)
    return jsonify(body), 201


@app.route('/api/admin/schemes/<int:sid>', methods=['PUT'])
@require_admin
def admin_update_scheme(sid):
    data = read_json('schemes.json')
    body = request.json or {}
    updated = None
    for i, s in enumerate(data):
        if s.get('id') == sid:
            data[i] = {**s, **body, 'id': sid}
            updated = data[i]
            break
    if updated is None:
        return jsonify({'error': 'Not found'}), 404
    write_json('schemes.json', data)
    return jsonify(updated)


@app.route('/api/admin/schemes/<int:sid>', methods=['DELETE'])
@require_admin
def admin_delete_scheme(sid):
    data = read_json('schemes.json')
    data = [s for s in data if s.get('id') != sid]
    write_json('schemes.json', data)
    return jsonify({'ok': True})


# Farmers
@app.route('/api/farmers/login', methods=['POST'])
def farmer_login():
    body = request.json or {}
    number = body.get('number')
    if not number:
        return jsonify({'error': 'Missing number'}), 400
    farmers = read_json('farmers.json')
    f = next((x for x in farmers if x.get('number') == number), None)
    if f:
        return jsonify(f)
    return jsonify({'need_registration': True})


@app.route('/api/farmers', methods=['POST'])
def farmer_register():
    body = request.json or {}
    number = body.get('number')
    name = body.get('name')
    if not number or not name:
        return jsonify({'error': 'Missing number or name'}), 400
    farmers = read_json('farmers.json')
    if any(x.get('number') == number for x in farmers):
        f = next(x for x in farmers if x.get('number') == number)
        return jsonify(f), 200
    f = {'id': next_id(farmers), 'number': number, 'name': name}
    farmers.append(f)
    write_json('farmers.json', farmers)
    return jsonify(f), 201


@app.route('/api/farmers/<int:fid>', methods=['PUT'])
def farmer_update(fid):
    farmers = read_json('farmers.json')
    body = request.json or {}
    updated = None
    for i, f in enumerate(farmers):
        if f.get('id') == fid:
            farmers[i] = {**f, **{k: v for k, v in body.items() if k != 'id'}}
            updated = farmers[i]
            break
    if updated is None:
        return jsonify({'error': 'Not found'}), 404
    write_json('farmers.json', farmers)
    return jsonify(updated)


# Dashboard
@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    expenses = read_json('expenses.json')
    income = read_json('income.json')
    rentals = read_json('rentals.json')
    farmer_id = request.args.get('farmer_id') or request.args.get('number')
    if farmer_id:
        expenses = [e for e in expenses if str(e.get('farmer_id') or e.get('farmer_number') or '') == str(farmer_id)]
        income = [i for i in income if str(i.get('farmer_id') or i.get('farmer_number') or '') == str(farmer_id)]
        rentals = [r for r in rentals if str(r.get('farmer_id') or r.get('farmer_number') or '') == str(farmer_id)]
    total_expense = sum(e.get('amount', 0) for e in expenses)
    total_income = sum(i.get('total', 0) for i in income)
    profit = total_income - total_expense
    rental_revenue = sum(r.get('paid_amount', 0) for r in rentals)
    rental_pending = sum((r.get('total_amount', 0) - r.get('paid_amount', 0)) for r in rentals)
    crop_stats = {}
    for e in expenses:
        c = e.get('crop', '—')
        crop_stats.setdefault(c, {'expense': 0, 'income': 0})
        crop_stats[c]['expense'] += e.get('amount', 0)
    for i in income:
        c = i.get('crop', '—')
        crop_stats.setdefault(c, {'expense': 0, 'income': 0})
        crop_stats[c]['income'] += i.get('total', 0)
    crops_summary = [
        {'crop': k, 'expense': v['expense'], 'income': v['income'], 'profit': v['income'] - v['expense']}
        for k, v in crop_stats.items()
    ]
    return jsonify({
        'total_expense': total_expense,
        'total_income': total_income,
        'net_profit': profit,
        'rental_revenue': rental_revenue,
        'rental_pending': rental_pending,
        'crops_summary': crops_summary,
        'recent_expenses': expenses[-5:][::-1],
        'recent_income': income[-3:][::-1]
    })


# Expenses
@app.route('/api/expenses', methods=['GET'])
def get_expenses():
    data = read_json('expenses.json')
    season = request.args.get('season')
    crop = request.args.get('crop')
    farmer_id = request.args.get('farmer_id') or request.args.get('number')
    if season:
        data = [e for e in data if e.get('season') == season]
    if crop:
        data = [e for e in data if e.get('crop') == crop]
    if farmer_id:
        data = [e for e in data if str(e.get('farmer_id') or e.get('farmer_number') or '') == str(farmer_id)]
    return jsonify(data)


@app.route('/api/expenses', methods=['POST'])
def add_expense():
    data = read_json('expenses.json')
    body = request.json or {}
    body['id'] = next_id(data)
    body['date'] = body.get('date', datetime.now().strftime('%Y-%m-%d'))
    if 'farmer_id' in body or 'farmer_number' in body:
        body['farmer_id'] = body.get('farmer_id', body.get('farmer_number'))
    data.append(body)
    write_json('expenses.json', data)
    return jsonify(body), 201


@app.route('/api/expenses/<int:eid>', methods=['DELETE'])
def delete_expense(eid):
    data = read_json('expenses.json')
    data = [e for e in data if e.get('id') != eid]
    write_json('expenses.json', data)
    return jsonify({'message': 'Deleted'})


# Income
@app.route('/api/income', methods=['GET'])
def get_income():
    data = read_json('income.json')
    farmer_id = request.args.get('farmer_id') or request.args.get('number')
    if farmer_id:
        data = [i for i in data if str(i.get('farmer_id') or i.get('farmer_number') or '') == str(farmer_id)]
    return jsonify(data)


@app.route('/api/income', methods=['POST'])
def add_income():
    data = read_json('income.json')
    body = request.json or {}
    body['id'] = next_id(data)
    body['total'] = body.get('quantity_kg', 0) * body.get('price_per_kg', 0)
    body['date'] = body.get('date', datetime.now().strftime('%Y-%m-%d'))
    if 'farmer_id' in body or 'farmer_number' in body:
        body['farmer_id'] = body.get('farmer_id', body.get('farmer_number'))
    data.append(body)
    write_json('income.json', data)
    return jsonify(body), 201


@app.route('/api/income/<int:iid>', methods=['DELETE'])
def delete_income(iid):
    data = read_json('income.json')
    data = [i for i in data if i.get('id') != iid]
    write_json('income.json', data)
    return jsonify({'message': 'Deleted'})


# Schemes
@app.route('/api/schemes', methods=['GET'])
def get_schemes():
    data = read_json('schemes.json')
    category = request.args.get('category')
    stype = request.args.get('type')
    if category:
        data = [s for s in data if s.get('category') == category]
    if stype:
        data = [s for s in data if s.get('type') == stype]
    return jsonify(data)


# Tractors
@app.route('/api/tractors', methods=['GET'])
def get_tractors():
    data = read_json('tractors.json')
    status = request.args.get('status')
    if status:
        data = [t for t in data if t.get('status') == status]
    return jsonify(data)


@app.route('/api/tractors', methods=['POST'])
def add_tractor():
    data = read_json('tractors.json')
    body = request.json or {}
    body['id'] = next_id(data)
    body['status'] = 'Available'
    data.append(body)
    write_json('tractors.json', data)
    return jsonify(body), 201


@app.route('/api/tractors/<int:tid>', methods=['DELETE'])
def delete_tractor(tid):
    data = read_json('tractors.json')
    data = [t for t in data if t.get('id') != tid]
    write_json('tractors.json', data)
    return jsonify({'message': 'Deleted'})


# Rentals
@app.route('/api/rentals', methods=['GET'])
def get_rentals():
    return jsonify(read_json('rentals.json'))


@app.route('/api/rentals', methods=['POST'])
def add_rental():
    rentals = read_json('rentals.json')
    tractors = read_json('tractors.json')
    body = request.json or {}
    body['id'] = next_id(rentals)
    
    # Handle start_date (required)
    s = datetime.strptime(body['start_date'], '%Y-%m-%dT%H:%M' if 'T' in body['start_date'] else '%Y-%m-%d')
    
    # Handle end_date (optional for initial booking)
    days = 0
    if body.get('end_date'):
        e = datetime.strptime(body['end_date'], '%Y-%m-%dT%H:%M' if 'T' in body['end_date'] else '%Y-%m-%d')
        days = max((e - s).days, 1)
        body['days'] = days
    else:
        body['end_date'] = None
        body['days'] = 0
    
    tractor = next((t for t in tractors if t.get('id') == body.get('tractor_id')), None)
    if tractor:
        body['tractor_name'] = tractor.get('name')
        # Only calculate total_amount if end_date is provided
        if body.get('end_date'):
            body['total_amount'] = days * tractor.get('rate_per_day', 0)
        else:
            body['total_amount'] = body.get('total_amount', 0)  # Initially 0 for pending rentals
        
        for t in tractors:
            if t.get('id') == body.get('tractor_id'):
                t['status'] = 'Rented'
        write_json('tractors.json', tractors)
    
    body['paid_amount'] = body.get('paid_amount', 0)
    paid = body['paid_amount']
    total = body.get('total_amount', 0)
    
    if total == 0:
        body['payment_status'] = 'Pending'  # No amount set yet - rental in progress
    elif paid == 0:
        body['payment_status'] = 'Pending'
    elif paid >= total:
        body['payment_status'] = 'Paid'
    else:
        body['payment_status'] = 'Partial'
    
    rentals.append(body)
    write_json('rentals.json', rentals)
    return jsonify(body), 201


@app.route('/api/rentals/<int:rid>/pay', methods=['PUT'])
def update_payment(rid):
    rentals = read_json('rentals.json')
    body = request.json or {}
    for r in rentals:
        if r.get('id') == rid:
            r['paid_amount'] = body.get('paid_amount', r.get('paid_amount', 0))
            r['payment_mode'] = body.get('payment_mode', r.get('payment_mode'))
            if r.get('paid_amount', 0) >= r.get('total_amount', 0):
                r['payment_status'] = 'Paid'
                tractors = read_json('tractors.json')
                for t in tractors:
                    if t.get('id') == r.get('tractor_id'):
                        t['status'] = 'Available'
                write_json('tractors.json', tractors)
            elif r.get('paid_amount', 0) > 0:
                r['payment_status'] = 'Partial'
            write_json('rentals.json', rentals)
            return jsonify(r)
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/rentals/<int:rid>', methods=['PUT'])
def complete_rental(rid):
    """Complete a rental by setting end_date and calculating total_amount"""
    rentals = read_json('rentals.json')
    tractors = read_json('tractors.json')
    body = request.json or {}
    
    for r in rentals:
        if r.get('id') == rid:
            # Update end_date if provided
            if body.get('end_date'):
                r['end_date'] = body.get('end_date')
                
                # Recalculate days and total amount
                try:
                    start = datetime.fromisoformat(r.get('start_date', '').replace('Z', '+00:00').split('T')[0] if 'T' not in r.get('start_date', '') else r.get('start_date', '').replace('Z', '+00:00'))
                    end = datetime.fromisoformat(body.get('end_date', '').replace('Z', '+00:00').split('T')[0] if 'T' not in body.get('end_date', '') else body.get('end_date', '').replace('Z', '+00:00'))
                    
                    diff_seconds = (end - start).total_seconds()
                    hours = max(1, round(diff_seconds / 3600))
                    days = hours // 24
                    extra_hours = hours % 24
                    
                    # Use hourly and daily rates
                    hourly_rate = 100
                    daily_rate = 800
                    total = days * daily_rate + extra_hours * hourly_rate
                    
                    r['total_amount'] = body.get('total_amount', total)
                    r['days'] = days
                except:
                    r['total_amount'] = body.get('total_amount', r.get('total_amount', 0))
            else:
                r['total_amount'] = body.get('total_amount', r.get('total_amount', 0))
            
            # Update payment status based on paid vs total
            paid = r.get('paid_amount', 0)
            total = r.get('total_amount', 0)
            if paid >= total:
                r['payment_status'] = 'Paid'
                # Mark tractor as available if rental is complete and paid
                if paid >= total:
                    for t in tractors:
                        if t.get('id') == r.get('tractor_id'):
                            t['status'] = 'Available'
                    write_json('tractors.json', tractors)
            elif paid > 0:
                r['payment_status'] = 'Partial'
            else:
                r['payment_status'] = 'Pending'
            
            write_json('rentals.json', rentals)
            return jsonify(r)
    
    return jsonify({'error': 'Rental not found'}), 404


@app.route('/api/rentals/<int:rid>', methods=['DELETE'])
def delete_rental(rid):
    rentals = read_json('rentals.json')
    rentals = [r for r in rentals if r.get('id') != rid]
    write_json('rentals.json', rentals)
    return jsonify({'message': 'Deleted'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
