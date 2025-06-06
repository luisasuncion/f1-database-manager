from flask import Flask, render_template, request, redirect, session, url_for, flash
from db import get_connection
import csv
from functools import wraps
from werkzeug.utils import secure_filename
import hashlib

# Iniciamos la aplicación Flask
app = Flask(__name__)
app.secret_key = 'secret'

def ms_para_hhmmss(ms):
    if ms is None:
        return '00:00:00'
    segundos = ms // 1000
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segundos_restantes = segundos % 60
    return f"{horas:02}:{minutos:02}:{segundos_restantes:02}"

# Decorador para verificar login básico
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'userid' not in session:
            flash('Por favor, faça login primeiro.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para verificar o tipo de usuário
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'tipo' not in session or session['tipo'] != role:
                flash('Acesso não autorizado.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Login 
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT userid, tipo, password, idoriginal FROM users WHERE login = %s", (login,))
        user = cur.fetchone()

        if user:
            # Generamos el hash SHA-256 del password digitado
            hashed_input = hashlib.sha256(password.encode('utf-8')).hexdigest()

            if hashed_input == user[2]:  # Comparación directa con lo que está en la base
                session['userid'] = user[0]
                session['tipo'] = user[1]
                
                if user[1] == 'Administrador':
                    return redirect(url_for('dashboard_admin'))
                elif user[1] == 'Escuderia':
                    session['constructor_id'] = user[3]
                    return redirect(url_for('dashboard_escuderia'))
                elif user[1] == 'Piloto':
                    session['driver_id'] = user[3]
                    return redirect(url_for('dashboard_piloto'))
            
        flash("Login ou senha inválidos", "danger")
        return render_template('login.html')
        
    return render_template('login.html')

# Administrador
@app.route('/admin')
@login_required
@role_required('Administrador')
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
    ORDER BY 1
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
@login_required
@role_required('Administrador')
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
                    flash("Já existe uma escuderia com esse ConstructorRef.", "escuderia_error")
                else:
                    cur.execute("""
                        INSERT INTO Constructors (ConstructorRef, Name, Nationality, Url)
                        VALUES (%s, %s, %s, %s)
                    """, (constructorref, name, nationality, url_field))
                    conn.commit()
                    flash("Escuderia cadastrada com sucesso!", "escuderia_success")

            elif 'driverref' in request.form:  # Cadastro de Piloto
                driverref = request.form['driverref'].strip().lower()
                number = request.form['number'] or None
                code = request.form['code'].strip()
                forename = request.form['forename'].strip()
                surname = request.form['surname'].strip()
                dob = request.form['dob']
                nationality = request.form['nationality'].strip()

                # Verificar se já existe
                cur.execute("SELECT 1 FROM Drivers WHERE lower(DriverRef) = %s", (driverref,))
                if cur.fetchone():
                    flash("Já existe um piloto com esse nome e sobrenome.", "piloto_error")
                else:
                    cur.execute("""
                        INSERT INTO Drivers (DriverRef, Number, Code, Forename, Surname, Dob, Nationality)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (driverref, number, code, forename, surname, dob, nationality))
                    conn.commit()
                    flash("Piloto cadastrado com sucesso!", "piloto_success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao inserir: {str(e)}", "escuderia_error")

    cur.close()
    conn.close()

    return render_template('acoes_admin.html')

@app.route('/admin/relatorios', methods=['GET', 'POST'])
@login_required
@role_required('Administrador')
def relatorios_admin():
    resultados = None
    relatorio_selecionado = None

    if request.method == 'POST':
        relatorio_selecionado = request.form.get('relatorio')

        conn = get_connection()
        cur = conn.cursor()

        if relatorio_selecionado == "relatorio1":
            cur.execute("""
                SELECT s.Status, COUNT(*) AS quantidade
                FROM Results r
                JOIN Status s ON r.StatusId = s.StatusId
                GROUP BY s.Status
                ORDER BY quantidade DESC;
            """)
            resultados = cur.fetchall()

        elif relatorio_selecionado == "relatorio2":
            cidade = request.form.get('cidade')

            conn = get_connection()
            cur = conn.cursor()

            cur.execute("""
                SELECT 
                    g.Name AS cidade_pesquisada,
                    a.IATACode,
                    a.Name AS aeroporto,
                    a.City AS cidade_aeroporto,
                    (earth_distance(ll_to_earth(g.Lat, g.Long), ll_to_earth(a.LatDeg, a.LongDeg))) / 1000 AS distancia_km,
                    a.Type
                FROM Airports a
                JOIN GeoCities15K g ON g.Name ILIKE %s AND g.Country = 'BR'
                WHERE a.IsoCountry = 'BR'
                AND a.Type IN ('large_airport', 'medium_airport')
                AND (earth_distance(ll_to_earth(g.Lat, g.Long), ll_to_earth(a.LatDeg, a.LongDeg))) <= 100000
                ORDER BY distancia_km;
            """, (cidade,))

            resultados = cur.fetchall()
            
        ## Relatorio 3 <- falta
        elif relatorio_selecionado == "relatorio3":

            conn = get_connection()
            cur = conn.cursor()

            # Nivel 1: Escuderias e quantidade de pilotos
            cur.execute("""
                SELECT 
                    c.Name AS escuderia,
                    COUNT(DISTINCT r.DriverId) AS total_pilotos
                FROM Constructors c
                LEFT JOIN Results r ON c.ConstructorId = r.ConstructorId
                GROUP BY c.Name
                ORDER BY c.Name;
            """)
            escuderias = cur.fetchall()

            # Nivel 2: Total de corridas
            cur.execute("SELECT COUNT(*) FROM Races;")
            total_corridas = cur.fetchone()[0]

            # Nivel 3: Corridas por circuito com min, max e avg
            cur.execute("""
                SELECT 
                    c.Name AS circuito,
                    MIN(res.Laps) AS min_voltas,
                    MAX(res.Laps) AS max_voltas,
                    AVG(res.Laps)::NUMERIC(10,2) AS media_voltas
                FROM Races r
                JOIN Circuits c ON r.CircuitId = c.CircuitId
                JOIN Results res ON r.RaceId = res.RaceId
                GROUP BY c.Name
                ORDER BY c.Name;
            """)
            circuitos = cur.fetchall()

            # Nivel 4: Corridas por circuito e tempo total
            cur.execute("""
                SELECT 
                    c.Name AS circuito,
                    r.Name AS corrida,
                    SUM(res.Laps) AS total_voltas,
                    SUM(res.Milliseconds) AS tempo_total_ms
                FROM Races r
                JOIN Circuits c ON r.CircuitId = c.CircuitId
                JOIN Results res ON r.RaceId = res.RaceId
                GROUP BY c.Name, r.Name
                ORDER BY c.Name, r.Name;
            """)
            corridas = cur.fetchall()
            corridas_formatadas = []

            for corrida in corridas:
                circuito = corrida[0]
                nome_corrida = corrida[1]
                total_voltas = corrida[2]
                tempo_total_ms = corrida[3]

                tempo_formatado = ms_para_hhmmss(tempo_total_ms)
                corridas_formatadas.append((circuito, nome_corrida, total_voltas, tempo_formatado))


            cur.close()
            conn.close()

            resultados = {
                "escuderias": escuderias,
                "total_corridas": total_corridas,
                "circuitos": circuitos,
                "corridas": corridas_formatadas
            }
        
        cur.close()
        conn.close()

    return render_template('relatorios_admin.html', resultados=resultados, relatorio_selecionado=relatorio_selecionado)

# Escuderia
@app.route('/escuderia')
@login_required
@role_required('Escuderia')
def dashboard_escuderia():
    constructor_id = session.get('constructor_id')

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT Name FROM Constructors WHERE ConstructorId = %s", (constructor_id,))
    result = cur.fetchone()

    if result is None:
        cur.close()
        conn.close()
        return "Escuderia não encontrada"

    session['constructor_name'] = result[0]

    cur.execute("SELECT total_vitorias_escuderia(%s);", (constructor_id,))
    vitorias = cur.fetchone()[0]

    cur.execute("SELECT total_pilotos_escuderia(%s);", (constructor_id,))
    total_pilotos = cur.fetchone()[0]

    cur.execute("SELECT * FROM anos_escuderia(%s);", (constructor_id,))
    anos = cur.fetchone()
    primeiro_ano, ultimo_ano = anos

    cur.close()
    conn.close()

    return render_template(
        'dashboard_escuderia.html',
        total_pilotos=total_pilotos,
        vitorias=vitorias,
        primeiro_ano=primeiro_ano,
        ultimo_ano=ultimo_ano
    )

@app.route('/escuderia/acoes', methods=['GET', 'POST'])
@login_required
@role_required('Escuderia')
def acoes_escuderia():
    conn = get_connection()
    cur = conn.cursor()
    
    pilotos = None  # Inicializamos vacío

    constructor_name = session.get('constructor_name')

    if request.method == 'POST':
        if 'forename' in request.form:
            forename = request.form['forename'].strip()
            constructor_id = session.get('constructor_id')

            cur.execute("""
                SELECT d.Forename, d.Surname, d.Dob, d.Nationality
                FROM Drivers d
                JOIN Results r ON d.DriverId = r.DriverId
                WHERE r.ConstructorId = %s AND d.Forename ILIKE %s
                GROUP BY d.Forename, d.Surname, d.Dob, d.Nationality
            """, (constructor_id, f"%{forename}%"))

            pilotos = cur.fetchall()

        elif 'arquivo' in request.files:
            file = request.files['arquivo']

            if not file:
                flash("Nenhum arquivo enviado.", "danger")
                return redirect(url_for('acoes_escuderia'))

            filename = secure_filename(file.filename)
            filepath = f"/tmp/{filename}"
            file.save(filepath)

            conn = get_connection()
            cur = conn.cursor()

            inseridos = 0
            repetidos = 0

            with open(filepath, newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    if len(row) < 8:
                        continue  # linha incompleta

                    driverref = row[0].strip().lower()
                    number = int(row[1].strip()) if row[1].strip() else None
                    code = row[2].strip()
                    forename = row[3].strip()
                    surname = row[4].strip()
                    dob = row[5].strip()
                    nationality = row[6].strip()
                    url = row[7].strip() if row[7].strip() else None

                    # Verificar duplicados por forename + surname
                    cur.execute("""
                        SELECT 1 FROM Drivers WHERE lower(Forename) = %s AND lower(Surname) = %s
                    """, (forename.lower(), surname.lower()))

                    if cur.fetchone():
                        repetidos += 1
                        continue

                    cur.execute("""
                        INSERT INTO Drivers (DriverRef, Number, Code, Forename, Surname, Dob, Nationality, Url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (driverref, number, code, forename, surname, dob, nationality, url))

                    inseridos += 1

            conn.commit()
            cur.close()
            conn.close()

            flash(f"{inseridos} pilotos inseridos com sucesso. {repetidos} já existiam.", "success")

    cur.close()
    conn.close()

    return render_template('acoes_escuderia.html', pilotos=pilotos)

@app.route('/escuderia/relatorios', methods=['GET', 'POST'])
@login_required
@role_required('Escuderia')
def relatorios_escuderia():
    resultados = None
    relatorio_selecionado = None
    constructor_id = session.get('constructor_id')

    if request.method == 'POST':
        relatorio_selecionado = request.form.get('relatorio')

        conn = get_connection()
        cur = conn.cursor()

        if relatorio_selecionado == "relatorio4":
            cur.execute("SELECT * FROM pilotos_vitorias(%s);", (constructor_id,))
            resultados = cur.fetchall()

        # relatorio5
        if relatorio_selecionado == "relatorio5":
            cur.execute("SELECT * FROM status_escuderia(%s);", (constructor_id,))
            resultados = cur.fetchall()

        cur.close()
        conn.close()

    return render_template('relatorios_escuderia.html', resultados=resultados, relatorio_selecionado=relatorio_selecionado)

# Pilotos
@app.route('/piloto')
@login_required
@role_required('Piloto')
def dashboard_piloto():
    driver_id = session.get('driver_id')  # ID do piloto logado

    conn = get_connection()
    cur = conn.cursor()

    # Buscar nome do piloto
    cur.execute("SELECT Forename, Surname FROM Drivers WHERE DriverId = %s", (driver_id,))
    piloto_result = cur.fetchone()

    if piloto_result is None:
        flash("Piloto não encontrado.", "danger")
        return redirect(url_for('login'))

    forename, surname = piloto_result
    nome_piloto = f"{forename} {surname}"
    session['nome_piloto'] = nome_piloto

    # Buscar escuderia atual do piloto (se já participou de alguma corrida)
    cur.execute("""
        SELECT c.Name
        FROM Constructors c
        JOIN Results res ON c.ConstructorId = res.ConstructorId
        WHERE res.DriverId = %s
        LIMIT 1
    """, (driver_id,))
    escuderia_result = cur.fetchone()

    if escuderia_result:
        session['escuderia'] = escuderia_result[0]
    else:
        session['escuderia'] = "Sem Escuderia"

    # Buscar anos (primeiro e último)
    cur.execute("SELECT * FROM anos_piloto(%s)", (driver_id,))
    anos = cur.fetchone()

    if anos and anos[0] and anos[1]:
        primeiro_ano, ultimo_ano = anos
    else:
        primeiro_ano, ultimo_ano = '-', '-'

    # Buscar resumo de competições
    cur.execute("SELECT * FROM resumo_competicoes_piloto(%s)", (driver_id,))
    competicoes = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'dashboard_piloto.html',
        primeiro_ano=primeiro_ano,
        ultimo_ano=ultimo_ano,
        competicoes=competicoes
    )

@app.route('/piloto/relatorios', methods = ['GET', 'POST'])
@login_required
@role_required('Piloto')
def relatorios_piloto():
    resultados = None
    relatorio_selecionado = None
    driver_id = session.get('driver_id')

    if request.method == 'POST':
        relatorio_selecionado = request.form.get('relatorio')

        conn = get_connection()
        cur = conn.cursor()

        if relatorio_selecionado == "relatorio6":
            cur.execute("SELECT * FROM pontos_por_ano(%s);", (driver_id,))
            resultados = cur.fetchall()

        if relatorio_selecionado == "relatorio7":
            cur.execute("SELECT * FROM status_piloto(%s);", (driver_id,))
            resultados = cur.fetchall()

        cur.close()
        conn.close()

    return render_template('relatorios_piloto.html', resultados=resultados, relatorio_selecionado=relatorio_selecionado)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
