from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import sqlite3
import datetime
import hashlib
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

app = Flask(__name__)
app.secret_key = 'rahasia_kas_kelas_67890'

# ================== DATABASE ==================
def init_db():
    conn = sqlite3.connect('kas_kelas.db')
    c = conn.cursor()
    
    # Anggota
    c.execute('''CREATE TABLE IF NOT EXISTS anggota (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT UNIQUE NOT NULL,
        kelas TEXT
    )''')
    
    # Transaksi
    c.execute('''CREATE TABLE IF NOT EXISTS transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anggota_id INTEGER,
        tanggal TEXT NOT NULL,
        jenis TEXT NOT NULL,
        kategori TEXT,
        nominal INTEGER NOT NULL,
        keterangan TEXT,
        FOREIGN KEY(anggota_id) REFERENCES anggota(id)
    )''')
    
    # Settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('iuran_bulanan', '20000')")
    
    # Users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )''')
    
    # Admin
    admin_pass = hashlib.sha256('Aisannous987'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
              ('admin', admin_pass, 'admin'))
    
    # User bersama
    user_pass = hashlib.sha256('kelas123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
              ('user', user_pass, 'user'))
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect('kas_kelas.db')
    conn.row_factory = sqlite3.Row
    return conn

def is_admin():
    return session.get('role') == 'admin'

# ================== HALAMAN ==================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()
        if user and user['password'] == hashlib.sha256(password.encode()).hexdigest():
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Username atau Password salah!')
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return render_template('admin.html', username=session.get('username'))
    else:
        return render_template('user.html', username=session.get('username'))

# ================== API ==================
@app.route('/api/dashboard')
def api_dashboard():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT SUM(nominal) as total FROM transaksi WHERE jenis='pemasukan'")
    total_in = cur.fetchone()['total'] or 0
    cur.execute("SELECT SUM(nominal) as total FROM transaksi WHERE jenis='pengeluaran'")
    total_out = cur.fetchone()['total'] or 0
    saldo = total_in - total_out
    cur.execute("SELECT COUNT(*) as count FROM anggota")
    total_anggota = cur.fetchone()['count']
    conn.close()
    return jsonify({
        'saldo': saldo,
        'total_in': total_in,
        'total_out': total_out,
        'total_anggota': total_anggota
    })

# --- Grafik: pemasukan vs pengeluaran per bulan (6 bulan terakhir) ---
@app.route('/api/chart_data')
def api_chart_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    # Ambil 6 bulan terakhir
    today = datetime.date.today()
    months = []
    labels = []
    for i in range(5, -1, -1):
        m = today.replace(day=1) - datetime.timedelta(days=30*i)
        months.append(m.strftime('%Y-%m'))
        labels.append(m.strftime('%b %Y'))
    
    pemasukan = []
    pengeluaran = []
    for bulan in months:
        cur.execute("SELECT SUM(nominal) FROM transaksi WHERE jenis='pemasukan' AND strftime('%Y-%m', tanggal) = ?", (bulan,))
        pemasukan.append(cur.fetchone()[0] or 0)
        cur.execute("SELECT SUM(nominal) FROM transaksi WHERE jenis='pengeluaran' AND strftime('%Y-%m', tanggal) = ?", (bulan,))
        pengeluaran.append(cur.fetchone()[0] or 0)
    conn.close()
    return jsonify({
        'labels': labels,
        'pemasukan': pemasukan,
        'pengeluaran': pengeluaran
    })

# --- Anggota ---
@app.route('/api/anggota', methods=['GET', 'POST', 'DELETE'])
def api_anggota():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute("SELECT * FROM anggota ORDER BY id DESC")
        data = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(data)
    if not is_admin():
        return jsonify({'error': 'Hanya Admin'}), 403
    if request.method == 'POST':
        data = request.get_json()
        nama = data.get('nama')
        kelas = data.get('kelas', '')
        if not nama:
            return jsonify({'error': 'Nama wajib'}), 400
        try:
            cur.execute("INSERT INTO anggota (nama, kelas) VALUES (?, ?)", (nama, kelas))
            conn.commit()
            conn.close()
            return jsonify({'message': 'Anggota ditambahkan'})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'error': 'Nama sudah ada'}), 400
    if request.method == 'DELETE':
        data = request.get_json()
        id_anggota = data.get('id')
        if not id_anggota:
            return jsonify({'error': 'ID diperlukan'}), 400
        cur.execute("DELETE FROM anggota WHERE id = ?", (id_anggota,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Anggota dihapus'})

# --- Transaksi ---
@app.route('/api/transaksi', methods=['GET', 'POST', 'DELETE'])
def api_transaksi():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'GET':
        bulan = request.args.get('bulan')
        query = """
            SELECT t.*, a.nama as nama_anggota 
            FROM transaksi t
            LEFT JOIN anggota a ON t.anggota_id = a.id
        """
        params = []
        if bulan:
            query += " WHERE strftime('%Y-%m', t.tanggal) = ?"
            params.append(bulan)
        query += " ORDER BY t.tanggal DESC, t.id DESC"
        cur.execute(query, params)
        data = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(data)
    if not is_admin():
        return jsonify({'error': 'Hanya Admin'}), 403
    if request.method == 'POST':
        data = request.get_json()
        anggota_id = data.get('anggota_id')
        tanggal = data.get('tanggal', datetime.date.today().isoformat())
        jenis = data.get('jenis')
        kategori = data.get('kategori', 'Lainnya')
        nominal = data.get('nominal')
        keterangan = data.get('keterangan', '')
        if not jenis or not nominal or nominal <= 0:
            return jsonify({'error': 'Data tidak valid'}), 400
        if jenis == 'pemasukan' and not anggota_id:
            return jsonify({'error': 'Pilih anggota untuk pemasukan'}), 400
        cur.execute("""
            INSERT INTO transaksi (anggota_id, tanggal, jenis, kategori, nominal, keterangan)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (anggota_id, tanggal, jenis, kategori, nominal, keterangan))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Transaksi berhasil'})
    if request.method == 'DELETE':
        data = request.get_json()
        id_trans = data.get('id')
        if not id_trans:
            return jsonify({'error': 'ID diperlukan'}), 400
        cur.execute("DELETE FROM transaksi WHERE id = ?", (id_trans,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Transaksi dihapus'})

# --- Status ---
@app.route('/api/status')
def api_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='iuran_bulanan'")
    row = cur.fetchone()
    target_iuran = int(row['value']) if row else 20000
    cur.execute("SELECT id, nama FROM anggota")
    anggota_list = cur.fetchall()
    hasil = []
    for anggota in anggota_list:
        cur.execute("""
            SELECT SUM(nominal) as total 
            FROM transaksi 
            WHERE anggota_id = ? AND jenis='pemasukan' 
            AND strftime('%Y-%m', tanggal) = ?
        """, (anggota['id'], bulan))
        total_bayar = cur.fetchone()['total'] or 0
        status = 'Lunas' if total_bayar >= target_iuran else 'Belum'
        hasil.append({
            'id': anggota['id'],
            'nama': anggota['nama'],
            'total_bayar': total_bayar,
            'target': target_iuran,
            'status': status
        })
    conn.close()
    return jsonify({
        'bulan': bulan,
        'target_iuran': target_iuran,
        'data': hasil
    })

# --- Settings ---
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute("SELECT key, value FROM settings")
        data = {row['key']: row['value'] for row in cur.fetchall()}
        conn.close()
        return jsonify(data)
    if not is_admin():
        return jsonify({'error': 'Hanya Admin'}), 403
    if request.method == 'POST':
        data = request.get_json()
        iuran = data.get('iuran_bulanan')
        if iuran:
            cur.execute("UPDATE settings SET value = ? WHERE key = 'iuran_bulanan'", (str(iuran),))
            conn.commit()
        conn.close()
        return jsonify({'message': 'Pengaturan berhasil diubah'})

# ================== EXPORT EXCEL ==================
@app.route('/export/excel')
def export_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    conn = get_db()
    cur = conn.cursor()
    
    # Ambil data transaksi
    cur.execute("""
        SELECT t.tanggal, a.nama as anggota, t.jenis, t.kategori, t.nominal, t.keterangan
        FROM transaksi t
        LEFT JOIN anggota a ON t.anggota_id = a.id
        WHERE strftime('%Y-%m', t.tanggal) = ?
        ORDER BY t.tanggal DESC
    """, (bulan,))
    rows = cur.fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Kas"
    
    # Header
    headers = ['Tanggal', 'Anggota', 'Jenis', 'Kategori', 'Nominal', 'Keterangan']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
        cell.alignment = Alignment(horizontal='center')
    
    # Data
    for r, row in enumerate(rows, 2):
        ws.cell(row=r, column=1, value=row['tanggal'])
        ws.cell(row=r, column=2, value=row['anggota'] or 'Umum')
        ws.cell(row=r, column=3, value=row['jenis'])
        ws.cell(row=r, column=4, value=row['kategori'] or '-')
        ws.cell(row=r, column=5, value=row['nominal'])
        ws.cell(row=r, column=6, value=row['keterangan'] or '-')
    
    # Auto column width
    for col in range(1, 7):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].auto_size = True
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'laporan_kas_{bulan}.xlsx')

# ================== EXPORT PDF ==================
@app.route('/export/pdf')
def export_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.tanggal, a.nama as anggota, t.jenis, t.kategori, t.nominal, t.keterangan
        FROM transaksi t
        LEFT JOIN anggota a ON t.anggota_id = a.id
        WHERE strftime('%Y-%m', t.tanggal) = ?
        ORDER BY t.tanggal DESC
    """, (bulan,))
    rows = cur.fetchall()
    conn.close()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=1, spaceAfter=12)
    elements.append(Paragraph(f'Laporan Kas Kelas - {bulan}', title_style))
    elements.append(Spacer(1, 0.5*cm))
    
    # Tabel
    data = [['Tanggal', 'Anggota', 'Jenis', 'Kategori', 'Nominal (Rp)', 'Keterangan']]
    for row in rows:
        data.append([
            row['tanggal'],
            row['anggota'] or 'Umum',
            row['jenis'],
            row['kategori'] or '-',
            f"{row['nominal']:,}",
            row['keterangan'] or '-'
        ])
    
    table = Table(data, colWidths=[2*cm, 3*cm, 2.5*cm, 2.5*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTSIZE', (0,1), (-1,-1), 8),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=True, download_name=f'laporan_kas_{bulan}.pdf')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)