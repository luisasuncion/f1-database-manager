import psycopg2

def get_connection():
    conn = psycopg2.connect(
        host="143.107.183.82",
        database="SCC241_Grupo1",
        user="SCC241_Ari_Aguilar",
        password="grupo1_Ari_2025"
    )
    return conn
