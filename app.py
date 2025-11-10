from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import paramiko
import subprocess
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

PROFILES_FILE = 'profiles.json'

def load_profiles():
    if os.path.exists(PROFILES_FILE):
        with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_profiles(profiles):
    with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, indent=4, ensure_ascii=False)

# ========== ROTAS PRINCIPAIS ==========

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    return jsonify(load_profiles())

@app.route('/api/profiles', methods=['POST'])
def save_profile():
    profiles = load_profiles()
    data = request.json
    
    profile_name = data.get('name')
    if not profile_name:
        return jsonify({'error': 'Nome do perfil é obrigatório'}), 400
    
    profiles[profile_name] = {
        'host': data.get('host'),
        'port': data.get('port', '5432'),
        'db': data.get('db'),
        'user': data.get('user'),
        'password': data.get('password'),
        'ssh_user': data.get('ssh_user', 'root'),
        'ssh_pass': data.get('ssh_pass'),
        'tipo_posto': data.get('tipo_posto', True)
    }
    
    save_profiles(profiles)
    return jsonify({'message': f'Perfil {profile_name} salvo com sucesso!'})

@app.route('/api/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    profiles = load_profiles()
    if name in profiles:
        del profiles[name]
        save_profiles(profiles)
        return jsonify({'message': f'Perfil {name} excluído!'})
    return jsonify({'error': 'Perfil não encontrado'}), 404

@app.route('/api/test/db', methods=['POST'])
def test_db_connection():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password'],
            connect_timeout=5
        )
        conn.close()
        return jsonify({'message': f'Conexão com {profile_name} bem-sucedida!'})
    except Exception as e:
        return jsonify({'error': f'Falha na conexão: {str(e)}'}), 500

@app.route('/api/test/ssh', methods=['POST'])
def test_ssh_connection():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    host = profile.get('host')
    ssh_user = profile.get('ssh_user')
    ssh_pass = profile.get('ssh_pass')
    
    if not all([host, ssh_user, ssh_pass]):
        return jsonify({'error': 'SSH não configurado'}), 400
    
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            username=ssh_user,
            password=ssh_pass,
            timeout=10
        )
        client.close()
        return jsonify({'message': f'Conexão SSH com {profile_name} bem-sucedida!'})
    except Exception as e:
        return jsonify({'error': f'Falha SSH: {str(e)}'}), 500

@app.route('/api/operations/processar-prevenda', methods=['POST'])
def processar_prevenda():
    data = request.json
    profile_name = data.get('profile_name')
    numero = data.get('numero')
    
    if not numero:
        return jsonify({'error': 'Número da pré-venda é obrigatório'}), 400
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        cursor.execute("SELECT processar_prevenda(%s);", (numero,))
        conn.commit()
        conn.close()
        return jsonify({'message': f'Pré-venda {numero} processada com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao processar pré-venda: {str(e)}'}), 500

@app.route('/api/operations/finalizar-pid-modulo', methods=['POST'])
def finalizar_pid_modulo():
    data = request.json
    profile_name = data.get('profile_name')
    modulo = data.get('modulo')
    
    if not modulo:
        return jsonify({'error': 'Módulo não especificado'}), 400
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(CASE WHEN pg_terminate_backend(pid) THEN 1 ELSE 0 END)
            FROM usuario_pid
            WHERE modulo = %s;
        """, (modulo,))
        
        result = cursor.fetchone()
        qtd = result[0] or 0 if result else 0
        
        conn.commit()
        conn.close()
        return jsonify({'message': f'{qtd} PID(s) do módulo {modulo} finalizado(s)!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao finalizar PID: {str(e)}'}), 500

@app.route('/api/operations/finalizar-pid-codigo', methods=['POST'])
def finalizar_pid_codigo():
    data = request.json
    profile_name = data.get('profile_name')
    pid = data.get('pid')
    
    if not pid:
        return jsonify({'error': 'PID não especificado'}), 400
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
        conn.commit()
        conn.close()
        return jsonify({'message': f'PID {pid} finalizado com sucesso!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao finalizar PID: {str(e)}'}), 500

@app.route('/api/operations/conexoes-ativas', methods=['POST'])
def conexoes_ativas():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pid, usename, application_name, client_addr,
                   now() - backend_start as tempo, COALESCE(query,'')
            FROM pg_stat_activity
            WHERE pid <> pg_backend_pid()
              AND datname = current_database()
            ORDER BY pid;
        """)
        
        conexoes = []
        for pid, user, app, ip, tempo, query in cursor.fetchall():
            tempo_s = str(tempo).split(".")[0]
            conexoes.append({
                'pid': pid,
                'usuario': user,
                'aplicacao': app,
                'ip': ip,
                'tempo': tempo_s,
                'query': query[:60]
            })
        
        conn.close()
        return jsonify({'conexoes': conexoes})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar conexões: {str(e)}'}), 500

@app.route('/api/operations/finalizar-todos-pids', methods=['POST'])
def finalizar_todos_pids():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid();
        """)
        
        result = cursor.fetchone()
        qtd = result[0] or 0
        
        conn.commit()
        conn.close()
        return jsonify({'message': f'{qtd} conexões finalizadas com sucesso!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao finalizar conexões: {str(e)}'}), 500

@app.route('/api/operations/liberar-produtos', methods=['POST'])
def liberar_produtos():
    data = request.json
    profile_name = data.get('profile_name')
    codigos = data.get('codigos', [])
    
    if not codigos:
        return jsonify({'error': 'Códigos não especificados'}), 400
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        sql = """
        INSERT INTO exc_br_inclusao_cadastro
            (empresa, produto, setor, tipo, usuario, data_cadastro, numero, status, livre)
        SELECT DISTINCT t.*
        FROM (
            SELECT ex.empresa, p.grid, 2, 2, 'LZT', CURRENT_DATE, p.codigo::int8, 'N', TRUE
            FROM exc_br_config ex
            JOIN empresa e                 ON e.grid = ex.empresa
            JOIN deposito d                ON d.empresa = e.grid
            JOIN deposito_grupo_produto dgp ON dgp.deposito = d.grid
            JOIN produto p                 ON p.grupo = dgp.grupo
            WHERE p.codigo = ANY(%s)
        ) t
        LEFT JOIN exc_br_inclusao_cadastro ei
               ON ei.empresa = t.empresa AND ei.produto = t.grid
        WHERE ei.produto IS NULL;
        """
        
        cursor.execute(sql, (codigos,))
        conn.commit()
        conn.close()
        return jsonify({'message': f'{len(codigos)} produto(s) liberado(s) com sucesso!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao liberar produtos: {str(e)}'}), 500

@app.route('/api/operations/abastecimentos', methods=['POST'])
def get_abastecimentos():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT codigo, bico, quantidade, valor, hora, dia_fiscal
            FROM abastecimento
            ORDER BY codigo DESC
            LIMIT 500;
        """)
        
        abastecimentos = []
        for row in cursor.fetchall():
            abastecimentos.append({
                'codigo': row[0],
                'bico': row[1],
                'quantidade': row[2],
                'valor': row[3],
                'hora': row[4].strftime('%H:%M:%S') if row[4] else '',
                'dia_fiscal': row[5].strftime('%d/%m/%Y') if row[5] else ''
            })
        
        conn.close()
        return jsonify({'abastecimentos': abastecimentos})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar abastecimentos: {str(e)}'}), 500

@app.route('/api/operations/excluir-abastecimento', methods=['POST'])
def excluir_abastecimento():
    data = request.json
    profile_name = data.get('profile_name')
    codigo = data.get('codigo')
    
    if not codigo:
        return jsonify({'error': 'Código não especificado'}), 400
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM abastecimento WHERE codigo = %s;", (codigo,))
        conn.commit()
        conn.close()
        return jsonify({'message': f'Abastecimento {codigo} excluído com sucesso!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao excluir abastecimento: {str(e)}'}), 500

@app.route('/api/operations/limpar-sincronia', methods=['POST'])
def limpar_sincronia():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN pg_terminate_backend(pid) THEN 1 ELSE 0 END), 0)
            FROM usuario_pid
            WHERE modulo = 'sync';
        """)
        
        result = cursor.fetchone()
        qtd = result[0] or 0
        
        conn.commit()
        conn.close()
        return jsonify({'message': f'{qtd} sessão(ões) de sincronia finalizada(s)!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao limpar sincronia: {str(e)}'}), 500

@app.route('/api/operations/limpar-precos', methods=['POST'])
def limpar_precos():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN pg_terminate_backend(pid) THEN 1 ELSE 0 END), 0)
            FROM usuario_pid
            WHERE modulo = 'sync_precos';
        """)
        
        result = cursor.fetchone()
        qtd = result[0] or 0
        
        conn.commit()
        conn.close()
        return jsonify({'message': f'{qtd} sessão(ões) de sincronia de preços finalizada(s)!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao limpar preços: {str(e)}'}), 500

@app.route('/api/operations/limpar-smartpos', methods=['POST'])
def limpar_smartpos():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN pg_terminate_backend(pid) THEN 1 ELSE 0 END), 0)
            FROM usuario_pid
            WHERE modulo LIKE 'smart%%'
               OR modulo LIKE 'monitor_smart%%';
        """)
        
        result = cursor.fetchone()
        qtd = result[0] or 0
        
        conn.commit()
        conn.close()
        return jsonify({'message': f'{qtd} sessão(ões) do SmartPOS finalizada(s)!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao limpar SmartPOS: {str(e)}'}), 500

@app.route('/api/operations/executar-sincronia', methods=['POST'])
def executar_sincronia():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    host = profile.get('host')
    ssh_user = profile.get('ssh_user')
    ssh_pass = profile.get('ssh_pass')
    tipo_posto = profile.get('tipo_posto', True)
    
    if not all([host, ssh_user, ssh_pass]):
        return jsonify({'error': 'SSH não configurado'}), 400
    
    comando = "as_sync" if tipo_posto else "as_sync --db-profile=LOJA"
    tipo = "POSTO" if tipo_posto else "LOJA"
    
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=ssh_user, password=ssh_pass, timeout=30)
        
        stdin, stdout, stderr = client.exec_command(comando, get_pty=True, timeout=300)
        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')
        exit_code = stdout.channel.recv_exit_status()
        
        client.close()
        
        if exit_code == 0:
            return jsonify({
                'message': f'Sincronia executada com sucesso! (Tipo: {tipo})',
                'output': output[-500:]
            })
        else:
            return jsonify({
                'error': f'Falha na sincronia (código: {exit_code})',
                'details': error[-500:] or output[-500:]
            }), 500
            
    except Exception as e:
        return jsonify({'error': f'Erro na execução: {str(e)}'}), 500

@app.route('/api/operations/atualizar-sistema', methods=['POST'])
def atualizar_sistema():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    host = profile.get('host')
    ssh_user = profile.get('ssh_user')
    ssh_pass = profile.get('ssh_pass')
    
    if not all([host, ssh_user, ssh_pass]):
        return jsonify({'error': 'SSH não configurado'}), 400
    
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=ssh_user, password=ssh_pass, timeout=30)
        
        stdin, stdout, stderr = client.exec_command("as_update", get_pty=True, timeout=300)
        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')
        exit_code = stdout.channel.recv_exit_status()
        
        client.close()
        
        if exit_code == 0:
            return jsonify({
                'message': 'Sistema atualizado com sucesso!',
                'output': output[-500:]
            })
        else:
            return jsonify({
                'error': f'Falha na atualização (código: {exit_code})',
                'details': error[-500:] or output[-500:]
            }), 500
            
    except Exception as e:
        return jsonify({'error': f'Erro na atualização: {str(e)}'}), 500

@app.route('/api/operations/reiniciar-conexoes', methods=['POST'])
def reiniciar_conexoes():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid();
        """)
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Conexões encerradas com sucesso!'})
            
    except Exception as e:
        return jsonify({'error': f'Erro ao reiniciar conexões: {str(e)}'}), 500

@app.route('/api/operations/reiniciar-postgres', methods=['POST'])
def reiniciar_postgres():
    try:
        if os.name == "nt":
            subprocess.run(["net", "stop", "postgresql-x64-14"], capture_output=True, text=True)
            subprocess.run(["net", "start", "postgresql-x64-14"], capture_output=True, text=True)
        else:
            subprocess.run(["sudo", "systemctl", "restart", "postgresql"], capture_output=True, text=True)
        
        return jsonify({'message': 'PostgreSQL reiniciado com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao reiniciar PostgreSQL: {str(e)}'}), 500

@app.route('/api/operations/info-sistema', methods=['POST'])
def info_sistema():
    data = request.json
    profile_name = data.get('profile_name')
    
    profiles = load_profiles()
    if profile_name not in profiles:
        return jsonify({'error': 'Perfil não encontrado'}), 404
    
    profile = profiles[profile_name]
    
    try:
        conn = psycopg2.connect(
            host=profile['host'],
            port=profile['port'],
            database=profile['db'],
            user=profile['user'],
            password=profile['password']
        )
        cursor = conn.cursor()
        
        # Tamanho do banco
        cursor.execute("SELECT pg_database_size(current_database());")
        tamanho = cursor.fetchone()[0]
        
        # Versões das estações
        cursor.execute("""
            SELECT DISTINCT ON (estacao) estacao, versao, ts_atualizacao
            FROM versao_estacao
            WHERE EXTRACT(YEAR FROM ts_atualizacao) = EXTRACT(YEAR FROM CURRENT_DATE)
            ORDER BY estacao, ts_atualizacao DESC;
        """)
        
        estacoes = []
        for estacao, versao, ts in cursor.fetchall():
            estacoes.append({
                'estacao': estacao,
                'versao': versao,
                'ts_atualizacao': ts.strftime('%d/%m/%Y %H:%M') if ts else ''
            })
        
        conn.close()
        
        return jsonify({
            'tamanho_banco': round(tamanho/(1024**3), 2),
            'estacoes': estacoes,
            'status': 'online'
        })
            
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar informações: {str(e)}'}), 500

@app.route('/api/monitoring/data', methods=['POST'])
def get_monitoring_data():
    data = request.json
    profile_names = data.get('profiles', [])
    
    profiles = load_profiles()
    monitoring_data = {}
    
    for profile_name in profile_names:
        if profile_name not in profiles:
            continue
            
        profile = profiles[profile_name]
        
        if not profile.get('tipo_posto', True):
            continue
            
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=profile['host'],
                username=profile['ssh_user'],
                password=profile['ssh_pass'],
                timeout=10
            )
            
            commands = {
                'uptime': 'uptime -p',
                'cpuinfo': 'cat /proc/cpuinfo | grep "model name" | head -n1 | cut -d: -f2',
                'memory': 'free -m | grep Mem',
                'disk': 'df -h / | tail -1',
                'load': 'cat /proc/loadavg | cut -d" " -f1',
                'postgres': 'systemctl is-active postgresql 2>/dev/null || echo "inactive"',
                'postgres_version': 'psql --version 2>/dev/null | cut -d" " -f3 || echo "N/A"'
            }
            
            resultados = {}
            for key, cmd in commands.items():
                try:
                    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
                    resultados[key] = stdout.read().decode().strip()
                except:
                    resultados[key] = 'N/A'
            
            client.close()
            
            # Processar resultados
            processador = resultados.get('cpuinfo', 'N/A').strip()
            
            # Memória
            mem_parts = resultados.get('memory', '').split()
            mem_total_mb = int(mem_parts[1]) if len(mem_parts) > 1 else 0
            mem_used_mb = int(mem_parts[2]) if len(mem_parts) > 2 else 0
            mem_percent = (mem_used_mb / mem_total_mb) * 100 if mem_total_mb > 0 else 0
            
            # Disco
            disk_parts = resultados.get('disk', '').split()
            disk_total_str = disk_parts[1] if len(disk_parts) > 1 else '0G'
            disk_used_str = disk_parts[2] if len(disk_parts) > 2 else '0G'
            disk_percent = disk_parts[4].replace('%', '') if len(disk_parts) > 4 else '0'
            
            # CPU
            load_avg = float(resultados.get('load', 0)) if resultados.get('load', '0').replace('.', '').isdigit() else 0
            cpu_cores = os.cpu_count() or 1
            cpu_uso = min(100, (load_avg / cpu_cores) * 100)
            
            # PostgreSQL
            postgres_status = resultados.get('postgres') == 'active'
            postgres_version = resultados.get('postgres_version', 'N/A').split('.')[0] if '.' in resultados.get('postgres_version', '') else 'N/A'
            
            monitoring_data[profile_name] = {
                'online': True,
                'processador': processador,
                'cpu_uso': round(cpu_uso),
                'memoria_percent': round(mem_percent),
                'disco_percent': int(disk_percent),
                'uptime_short': resultados.get('uptime', '').replace('up ', '')[:8],
                'postgres_status': postgres_status,
                'postgres_version': postgres_version,
                'latencia': '5ms',
                'ultima_coleta': datetime.now().strftime('%H:%M')
            }
            
        except Exception as e:
            monitoring_data[profile_name] = {
                'online': False,
                'erro': str(e),
                'ultima_coleta': datetime.now().strftime('%H:%M:%S')
            }
    
    return jsonify(monitoring_data)

@app.route('/api/test/all', methods=['POST'])
def test_all_connections():
    profiles_data = load_profiles()
    results = []
    
    for profile_name, profile in profiles_data.items():
        # Teste de BD
        try:
            conn = psycopg2.connect(
                host=profile['host'],
                port=profile['port'],
                database=profile['db'],
                user=profile['user'],
                password=profile['password'],
                connect_timeout=5
            )
            conn.close()
            db_result = "BD OK"
        except Exception as e:
            db_result = f"BD: {str(e)[:40]}..."
        
        # Teste SSH
        ssh_result = "SSH N/C"
        if profile.get('host') and profile.get('ssh_user') and profile.get('ssh_pass'):
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=profile['host'],
                    username=profile['ssh_user'],
                    password=profile['ssh_pass'],
                    timeout=5
                )
                client.close()
                ssh_result = "SSH OK"
            except Exception as e:
                ssh_result = f"SSH: {str(e)[:40]}..."
        
        results.append(f"{profile_name}: {db_result} | {ssh_result}")
    
    return jsonify({'results': results})

@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    if not os.path.exists(PROFILES_FILE):
        save_profiles({})
    
    print("=" * 60)
    print("🚀 AWTECH GESTAO DE TI - BACKEND INICIADO")
    print("📡 Servidor rodando em: http://localhost:5000")
    print("=" * 60)
    
    app.run(debug=True, port=5000, host='0.0.0.0')