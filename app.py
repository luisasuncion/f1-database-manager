from flask import Flask, render_template, request, redirect, session, url_for, flash
from db import get_connection
import psycopg2

# Iniciamos la aplicación Flask
app = Flask(__name__)
app.secret_key = 'secret'

def ms_para_hhmmss(ms):
    segundos = ms // 1000
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segundos_restantes = segundos % 60
    return f"{horas:02}:{minutos:02}:{segundos_restantes:02}"


# Login 
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT userid, tipo, password FROM users WHERE login = %s", (login,))
        user = cur.fetchone()

        if user and password == user[2]:  # ⚠️ Falta el SCRAM-SHA-256
            session['userid'] = user[0]
            session['tipo'] = user[1]

            if user[1] == 'Administrador':
                return redirect(url_for('dashboard_admin'))
            elif user[1] == 'Escuderia':
                return redirect(url_for('dashboard_escuderia'))
            elif user[1] == 'Piloto':
                return redirect(url_for('dashboard_piloto'))
        else:
            return render_template('login.html', error="Login ou senha inválidos")
        
    return render_template('login.html')

@app.route('/admin')
def dashboard_admin():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM drivers")
    total_pilotos = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM constructors")
    total_escuderias = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM seasons")
    total_temporadas = cur.fetchone()[0]

    cur.execute("""
    SELECT r.Name, SUM(res.Laps), SUM(res.Milliseconds)
    FROM Races r
    JOIN Results res ON r.RaceId = res.RaceId
    WHERE r.Year = 2024
    GROUP BY r.Name
    """)
    corridas_raw = cur.fetchall()

    # Convertimos o tempo de milisegundos para hh:mm:ss
    corridas = []
    for row in corridas_raw:
        nome_corrida = row[0]
        total_voltas = row[1]
        tempo_total = ms_para_hhmmss(row[2]) if row[2] else '00:00:00'
        corridas.append((nome_corrida, total_voltas, tempo_total))

    # Escuderias do ano atual
    cur.execute("""
        SELECT c.Name, SUM(res.Points)
        FROM Constructors c
        JOIN Results res ON c.ConstructorId = res.ConstructorId
        JOIN Races r ON res.RaceId = r.RaceId
        WHERE r.Year = 2024
        GROUP BY c.Name
        ORDER BY 2 DESC
    """)
    escuderias = cur.fetchall()

    # Pilotos do ano atual
    cur.execute("""
        SELECT d.Forename || ' ' || d.Surname, SUM(res.Points)
        FROM drivers d
        JOIN Results res ON d.DriverId = res.DriverId
        JOIN Races r ON res.RaceId = r.RaceId
        WHERE r.Year = 2024
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    pilotos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'dashboard_admin.html',
        total_pilotos=total_pilotos,
        total_escuderias=total_escuderias,
        total_temporadas=total_temporadas,
        corridas=corridas,
        escuderias=escuderias,
        pilotos=pilotos
    )

@app.route('/admin/acoes' , methods=['GET', 'POST'])
def acoes_admin():
    conn = get_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        try:
            if 'constructorref' in request.form:  # Cadastro de Escuderia
                constructorref = request.form['constructorref'].strip().lower()
                name = request.form['name'].strip()
                nationality = request.form['nationality'].strip()
                url_field = request.form['url'].strip()

                # Verificar se já existe
                cur.execute("SELECT 1 FROM Constructors WHERE lower(ConstructorRef) = %s", (constructorref,))
                if cur.fetchone():
                    flash("Já existe uma escuderia com esse ConstructorRef.", "danger")
                else:
                    cur.execute("""
                        INSERT INTO Constructors (ConstructorRef, Name, Nationality, Url)
                        VALUES (%s, %s, %s, %s)
                    """, (constructorref, name, nationality, url_field))
                    conn.commit()
                    flash("Escuderia cadastrada com sucesso!", "success")

            elif 'driverref' in request.form:  # Cadastro de Piloto
                driverref = request.form['driverref'].strip().lower()
                number = request.form['number'] or None
                code = request.form['code'].strip()
                forename = request.form['forename'].strip()
                surname = request.form['surname'].strip()
                dob = request.form['dob']
                nationality = request.form['nationality'].strip()

                # Verificar se já existe
                cur.execute("SELECT 1 FROM Driver WHERE lower(DriverRef) = %s", (driverref,))
                if cur.fetchone():
                    flash("Já existe um piloto com esse DriverRef.", "danger")
                else:
                    cur.execute("""
                        INSERT INTO Driver (DriverRef, Number, Code, Forename, Surname, Dob, Nationality)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (driverref, number, code, forename, surname, dob, nationality))
                    conn.commit()
                    flash("Piloto cadastrado com sucesso!", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao inserir: {str(e)}", "danger")

    cur.close()
    conn.close()

    return render_template('acoes_admin.html')

@app.route('/escuderia')
def dashboard_escuderia():
    return render_template('dashboard_escuderia.html')

@app.route('/piloto')
def dashboard_piloto():
    return render_template('dashboard_piloto.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
