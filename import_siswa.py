import sqlite3
conn = sqlite3.connect('kas_kelas.db')
c = conn.cursor()

# Daftar siswa sudah diurutkan A-Z
siswa = [
    'Abdullah Ihza Dz',
    'Afikha Destianti',
    'Afiqah Febiola',
    'Arya Dika',
    'Ashifati Ashfa',
    'Basit Al Ghofur',
    'Davvi Taufiqurrahman',
    'Diaz Adnan Syahbani',
    'Eka Safrina Alifany',
    'Evalina Putri',
    'Fachri Rizqiawan',
    'Fadlan Aryo Pratama',
    'Hawri \'Ien Fadilah',
    'Inaya Savia Zahra',
    'Ismail Haniya Rahman',
    'Kayla Natasya Sofian',
    'Kirana Avrilia Sari',
    'M. Keanu Arief Sugiarto',
    'Muhammad Faeyza Ahnaf',
    'Muhammad Zidane',
    'Nadine Greaceana Nifili',
    'Nur Aura Saparani',
    'Nur Sabrina Oktaviani',
    'Queensha Hadinata',
    'Rasyid Farhan S',
    'Reffina Rayna Puteri',
    'Ribbyna Rasya D',
    'Satrio Budi Utomo',
    'Shaula Nafeeza',
    'Syahid Arsyil',
    'Syauqiyah AJP',
    'Tanisha Firyali Hasti',
    'Tri Oktavio Sandy'
]

for nama in siswa:
    c.execute("INSERT OR IGNORE INTO anggota (nama, kelas) VALUES (?, ?)", (nama, 'RPL 1'))

conn.commit()
conn.close()
print(f"✅ {len(siswa)} anggota berhasil ditambahkan!")
print("📋 Nama sudah diurutkan A-Z")