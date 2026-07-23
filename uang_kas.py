import os
import datetime
import hashlib
import random
import io
import psycopg2
from psycopg2 import pool
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm # type: ignore

app = Flask(__name__)
app.secret_key = 'rahasia_kas_kelas_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)

# ================== KONFIGURASI 2 DATABASE ==================
# 🔵 PRIMARY: Aiven (Gratis, 1GB)
AIVEN_URL = "postgres://avnadmin:AVNS_7JPxrd03DK3rRDxj_TC@pg-213d1eb5-cworthy553-e567.g.aivencloud.com:18553/defaultdb?sslmode=require"

# 🟢 SECONDARY: Supabase (Gratis, 500MB)
# GANTI PASSWORD_ASLI dengan password database Supabase-mu!
SUPABASE_URL = "postgresql://postgres 8DOoY7AiNauA9xYg@db.qzwruajhuirrmttomjth.supabase.co:5432/postgres"



# Connection Pools
primary_pool = psycopg2.pool.SimpleConnectionPool(1, 5, AIVEN_URL)
secondary_pool = psycopg2.pool.SimpleConnectionPool(1, 3, SUPABASE_URL)

def get_db_connection(use_primary=True):
    """Ambil koneksi dari pool yang dipilih"""
    try:
        if use_primary:
            return primary_pool.getconn()
        else:
            return secondary_pool.getconn()
    except:
        # Jika primary error, switch ke secondary
        print("⚠️ Primary DB error, switch ke Secondary!")
        return secondary_pool.getconn()

def close_db_connection(conn, use_primary=True):
    """Kembalikan koneksi ke pool"""
    if use_primary:
        primary_pool.putconn(conn)
    else:
        secondary_pool.putconn(conn)

def execute_smart_query(query, params=None, write_mode=False):
    """
    Eksekusi query dengan failover:
    - READ: coba primary dulu, kalau error pake secondary
    - WRITE (INSERT/UPDATE/DELETE): tulis di PRIMARY dan SECONDARY sekaligus
    """
    result = None
    primary_success = False
    secondary_success = False
    
    # 1. Coba PRIMARY dulu
    try:
        conn = get_db_connection(use_primary=True)
        c = conn.cursor()
        if params:
            c.execute(query, params)
        else:
            c.execute(query)
        if write_mode:
            conn.commit()
        else:
            result = c.fetchall()
        close_db_connection(conn, use_primary=True)
        primary_success = True
        print("✅ Primary DB success")
    except Exception as e:
        print(f"❌ Primary DB error: {e}")
    
    # 2. Kalau WRITE MODE, tulis juga ke SECONDARY (biar sinkron)
    if write_mode and primary_success:
        try:
            conn = get_db_connection(use_primary=False)
            c = conn.cursor()
            if params:
                c.execute(query, params)
            else:
                c.execute(query)
            conn.commit()
            close_db_connection(conn, use_primary=False)
            secondary_success = True
            print("✅ Secondary DB success (sync)")
        except Exception as e:
            print(f"⚠️ Secondary DB error: {e}")
    
    # 3. Kalau READ MODE dan primary gagal, coba secondary
    if not write_mode and not primary_success:
        try:
            conn = get_db_connection(use_primary=False)
            c = conn.cursor()
            if params:
                c.execute(query, params)
            else:
                c.execute(query)
            result = c.fetchall()
            close_db_connection(conn, use_primary=False)
            print("✅ Secondary DB success (failover)")
        except Exception as e:
            print(f"❌ Secondary DB error: {e}")
            return None
    
    return result

# ================== INISIALISASI TABEL (DI KEDUA DB) ==================
def init_db():
    """Buat tabel di PRIMARY dan SECONDARY sekaligus"""
    for url, name in [(AIVEN_URL, 'Aiven'), (SUPABASE_URL, 'Supabase')]:
        try:
            conn = psycopg2.connect(url)
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS anggota (
                    id SERIAL PRIMARY KEY,
                    nama TEXT UNIQUE NOT NULL,
                    kelas TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS transaksi (
                    id SERIAL PRIMARY KEY,
                    anggota_id INTEGER REFERENCES anggota(id),
                    tanggal TEXT NOT NULL,
                    jenis TEXT NOT NULL,
                    kategori TEXT,
                    nominal INTEGER NOT NULL,
                    keterangan TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            c.execute("INSERT INTO settings (key, value) VALUES ('iuran_bulanan', '20000') ON CONFLICT (key) DO NOTHING")
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL
                )
            ''')
            admin_pass = hashlib.sha256('Aisannous987'.encode()).hexdigest()
            c.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
                      ('admin', admin_pass, 'admin'))
            user_pass = hashlib.sha256('kelas123'.encode()).hexdigest()
            c.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
                      ('user', user_pass, 'user'))
            conn.commit()
            conn.close()
            print(f"✅ {name} ready!")
        except Exception as e:
            print(f"❌ {name} init error: {e}")

init_db()

# ================== SURPRISE ==================
SURPRISE_QUOTES = [
    "✨ Mantap! Transaksi berhasil!",
    "🎉 Yeay! Uang kas bertambah!",
    "💰 Saldo makin tebal!",
    "🌟 Kamu luar biasa!",
    "🚀 Transaksi sukses!",
    "🎊 Hore! Iuran masuk!",
    "💪 Semangat! Kas kelas sehat!"
]

def get_surprise():
    return random.choice(SURPRISE_QUOTES)

# ================== HALAMAN ==================
@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return render_template('admin.html', username=session.get('username'))
    else:
        return render_template('user.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        result = execute_smart_query(
            "SELECT * FROM users WHERE username = %s",
            (username,)
        )
        if result and len(result) > 0:
            user = result[0]
            if user[2] == hashlib.sha256(password.encode()).hexdigest():
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[3]
                session.permanent = True
                return redirect(url_for('dashboard'))
        return render_template('login.html', error='Username atau Password salah!')
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ================== API ==================
@app.route('/api/surprise')
def api_surprise():
    return jsonify({'message': get_surprise()})

@app.route('/api/dashboard')
def api_dashboard():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    total_in = execute_smart_query("SELECT COALESCE(SUM(nominal), 0) as total FROM transaksi WHERE jenis='pemasukan'")[0][0]
    total_out = execute_smart_query("SELECT COALESCE(SUM(nominal), 0) as total FROM transaksi WHERE jenis='pengeluaran'")[0][0]
    total_anggota = execute_smart_query("SELECT COUNT(*) as count FROM anggota")[0][0]
    
    return jsonify({
        'saldo': total_in - total_out,
        'total_in': total_in,
        'total_out': total_out,
        'total_anggota': total_anggota
    })

@app.route('/api/chart_data')
def api_chart_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    today = datetime.date.today()
    months = [today.replace(day=1) + datetime.timedelta(days=30*i) for i in range(6)]
    labels = [m.strftime('%b %Y') for m in months]
    
    pemasukan = []
    pengeluaran = []
    for m in months:
        bulan = m.strftime('%Y-%m')
        p = execute_smart_query(
            "SELECT COALESCE(SUM(nominal), 0) FROM transaksi WHERE jenis='pemasukan' AND tanggal LIKE %s",
            (bulan + '%',)
        )[0][0]
        pemasukan.append(p)
        q = execute_smart_query(
            "SELECT COALESCE(SUM(nominal), 0) FROM transaksi WHERE jenis='pengeluaran' AND tanggal LIKE %s",
            (bulan + '%',)
        )[0][0]
        pengeluaran.append(q)
    
    return jsonify({'labels': labels, 'pemasukan': pemasukan, 'pengeluaran': pengeluaran})

@app.route('/api/anggota', methods=['GET', 'POST', 'DELETE'])
def api_anggota():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if request.method == 'GET':
        result = execute_smart_query("SELECT * FROM anggota ORDER BY id DESC")
        data = [{'id': r[0], 'nama': r[1], 'kelas': r[2]} for r in result] if result else []
        return jsonify(data)
    
    if session.get('role') != 'admin':
        return jsonify({'error': 'Hanya Admin'}), 403
    
    if request.method == 'POST':
        data = request.get_json()
        nama = data.get('nama')
        kelas = data.get('kelas', '')
        if not nama:
            return jsonify({'error': 'Nama wajib'}), 400
        try:
            # WRITE ke kedua DB (sinkron)
            execute_smart_query(
                "INSERT INTO anggota (nama, kelas) VALUES (%s, %s)",
                (nama, kelas),
                write_mode=True
            )
            return jsonify({'message': 'Anggota ditambahkan'})
        except Exception as e:
            return jsonify({'error': 'Nama sudah ada'}), 400
    
    if request.method == 'DELETE':
        data = request.get_json()
        id_anggota = data.get('id')
        if not id_anggota:
            return jsonify({'error': 'ID diperlukan'}), 400
        execute_smart_query(
            "DELETE FROM anggota WHERE id = %s",
            (id_anggota,),
            write_mode=True
        )
        return jsonify({'message': 'Anggota dihapus'})

@app.route('/api/transaksi', methods=['GET', 'POST', 'DELETE'])
def api_transaksi():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if request.method == 'GET':
        bulan = request.args.get('bulan')
        if bulan:
            result = execute_smart_query("""
                SELECT t.*, a.nama as nama_anggota 
                FROM transaksi t
                LEFT JOIN anggota a ON t.anggota_id = a.id
                WHERE t.tanggal LIKE %s
                ORDER BY t.tanggal DESC, t.id DESC
            """, (bulan + '%',))
        else:
            result = execute_smart_query("""
                SELECT t.*, a.nama as nama_anggota 
                FROM transaksi t
                LEFT JOIN anggota a ON t.anggota_id = a.id
                ORDER BY t.tanggal DESC, t.id DESC
            """)
        data = []
        if result:
            for row in result:
                data.append({
                    'id': row[0],
                    'anggota_id': row[1],
                    'tanggal': row[2],
                    'jenis': row[3],
                    'kategori': row[4],
                    'nominal': row[5],
                    'keterangan': row[6],
                    'nama_anggota': row[7] if len(row) > 7 else None
                })
        return jsonify(data)
    
    if session.get('role') != 'admin':
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
        execute_smart_query(
            "INSERT INTO transaksi (anggota_id, tanggal, jenis, kategori, nominal, keterangan) VALUES (%s, %s, %s, %s, %s, %s)",
            (anggota_id, tanggal, jenis, kategori, nominal, keterangan),
            write_mode=True
        )
        return jsonify({'message': 'Transaksi berhasil'})
    
    if request.method == 'DELETE':
        data = request.get_json()
        id_trans = data.get('id')
        if not id_trans:
            return jsonify({'error': 'ID diperlukan'}), 400
        execute_smart_query(
            "DELETE FROM transaksi WHERE id = %s",
            (id_trans,),
            write_mode=True
        )
        return jsonify({'message': 'Transaksi dihapus'})

@app.route('/api/status')
def api_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    
    target_row = execute_smart_query("SELECT value FROM settings WHERE key='iuran_bulanan'")
    target = int(target_row[0][0]) if target_row else 20000
    
    anggota_result = execute_smart_query("SELECT id, nama FROM anggota")
    hasil = []
    if anggota_result:
        for anggota in anggota_result:
            total = execute_smart_query(
                "SELECT COALESCE(SUM(nominal), 0) as total FROM transaksi WHERE anggota_id = %s AND jenis='pemasukan' AND tanggal LIKE %s",
                (anggota[0], bulan + '%')
            )[0][0]
            status = 'Lunas' if total >= target else 'Belum'
            hasil.append({
                'id': anggota[0],
                'nama': anggota[1],
                'total_bayar': total,
                'target': target,
                'status': status
            })
    return jsonify({
        'bulan': bulan,
        'target_iuran': target,
        'data': hasil
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if session.get('role') != 'admin':
        return jsonify({'error': 'Hanya Admin'}), 403
    
    if request.method == 'GET':
        result = execute_smart_query("SELECT key, value FROM settings")
        data = {row[0]: row[1] for row in result} if result else {}
        return jsonify(data)
    
    if request.method == 'POST':
        data = request.get_json()
        iuran = data.get('iuran_bulanan')
        if iuran:
            execute_smart_query(
                "UPDATE settings SET value = %s WHERE key = 'iuran_bulanan'",
                (str(iuran),),
                write_mode=True
            )
        return jsonify({'message': 'Pengaturan berhasil diubah'})

@app.route('/api/bulk_payment', methods=['POST'])
def api_bulk_payment():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    tanggal = data.get('tanggal', datetime.date.today().isoformat())
    nominal = data.get('nominal')
    anggota_ids = data.get('anggota_ids', [])
    if not nominal or nominal <= 0:
        return jsonify({'error': 'Nominal tidak valid'}), 400
    if not anggota_ids:
        return jsonify({'error': 'Tidak ada anggota dipilih'}), 400
    for aid in anggota_ids:
        execute_smart_query(
            "INSERT INTO transaksi (anggota_id, tanggal, jenis, kategori, nominal, keterangan) VALUES (%s, %s, 'pemasukan', 'Iuran', %s, 'Bayar Cepat (Bulk)')",
            (aid, tanggal, nominal),
            write_mode=True
        )
    return jsonify({'message': f'✅ {len(anggota_ids)} anggota berhasil dibayar!', 'surprise': get_surprise()})

@app.route('/api/bulk_status')
def api_bulk_status():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    
    target_row = execute_smart_query("SELECT value FROM settings WHERE key='iuran_bulanan'")
    target = int(target_row[0][0]) if target_row else 20000
    
    anggota_result = execute_smart_query("SELECT id, nama, kelas FROM anggota ORDER BY nama")
    hasil = []
    if anggota_result:
        for a in anggota_result:
            total = execute_smart_query(
                "SELECT COALESCE(SUM(nominal), 0) as total FROM transaksi WHERE anggota_id = %s AND jenis='pemasukan' AND tanggal LIKE %s",
                (a[0], bulan + '%')
            )[0][0]
            hasil.append({
                'id': a[0],
                'nama': a[1],
                'kelas': a[2],
                'total_bayar': total,
                'target': target,
                'status': 'Lunas' if total >= target else 'Belum'
            })
    return jsonify(hasil)

@app.route('/export/excel')
def export_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    
    rows = execute_smart_query("""
        SELECT t.tanggal, a.nama as anggota, t.jenis, t.kategori, t.nominal, t.keterangan
        FROM transaksi t
        LEFT JOIN anggota a ON t.anggota_id = a.id
        WHERE t.tanggal LIKE %s
        ORDER BY t.tanggal DESC
    """, (bulan + '%',))
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Kas"
    headers = ['Tanggal', 'Anggota', 'Jenis', 'Kategori', 'Nominal', 'Keterangan']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
        cell.alignment = Alignment(horizontal='center')
    if rows:
        for r, row in enumerate(rows, 2):
            ws.cell(row=r, column=1, value=row[0])
            ws.cell(row=r, column=2, value=row[1] or 'Umum')
            ws.cell(row=r, column=3, value=row[2])
            ws.cell(row=r, column=4, value=row[3] or '-')
            ws.cell(row=r, column=5, value=row[4])
            ws.cell(row=r, column=6, value=row[5] or '-')
    for col in range(1, 7):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].auto_size = True
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'laporan_kas_{bulan}.xlsx')

@app.route('/export/pdf')
def export_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    bulan = request.args.get('bulan', datetime.date.today().strftime('%Y-%m'))
    
    rows = execute_smart_query("""
        SELECT t.tanggal, a.nama as anggota, t.jenis, t.kategori, t.nominal, t.keterangan
        FROM transaksi t
        LEFT JOIN anggota a ON t.anggota_id = a.id
        WHERE t.tanggal LIKE %s
        ORDER BY t.tanggal DESC
    """, (bulan + '%',))
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=1, spaceAfter=12)
    elements.append(Paragraph(f'Laporan Kas Kelas - {bulan}', title_style))
    elements.append(Spacer(1, 0.5*cm))
    data = [['Tanggal', 'Anggota', 'Jenis', 'Kategori', 'Nominal (Rp)', 'Keterangan']]
    if rows:
        for row in rows:
            data.append([
                row[0],
                row[1] or 'Umum',
                row[2],
                row[3] or '-',
                f"{row[4]:,}",
                row[5] or '-'
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
    app.run(debug=False, host='0.0.0.0', port=5000)