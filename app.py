import os
import json
import subprocess
import datetime
import threading
import shutil
import bcrypt
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, make_response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = os.urandom(24)

BASE_DIR = '/DATA/AppData/Btrfs-snapper'
RECORDS_DIR = os.path.join(BASE_DIR, 'records')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
PASSWORD_DIR = os.path.join(BASE_DIR, 'password')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

os.makedirs(RECORDS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(PASSWORD_DIR, exist_ok=True)

scheduler = BackgroundScheduler()

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {'max_storage_mb': 100, 'scheduled_tasks': [], 'manual_records': []}

def has_account():
    account_file = os.path.join(PASSWORD_DIR, 'account')
    return os.path.exists(account_file)

def create_account(username, password):
    account_file = os.path.join(PASSWORD_DIR, 'account')
    if os.path.exists(account_file):
        return False, '账户已存在'
    
    os.makedirs(PASSWORD_DIR, exist_ok=True)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with open(account_file, 'w') as f:
        json.dump({'username': username, 'password': hashed.decode()}, f)
    return True, '账户创建成功'

def get_failed_attempts():
    attempts_file = os.path.join(PASSWORD_DIR, 'attempts')
    if os.path.exists(attempts_file):
        with open(attempts_file, 'r') as f:
            return json.load(f)
    return {'count': 0, 'first_fail_time': None, 'locked_until': None}

def save_failed_attempts(attempts):
    attempts_file = os.path.join(PASSWORD_DIR, 'attempts')
    os.makedirs(PASSWORD_DIR, exist_ok=True)
    with open(attempts_file, 'w') as f:
        json.dump(attempts, f)

def check_locked():
    attempts = get_failed_attempts()
    if attempts.get('locked_until'):
        locked_until = datetime.datetime.fromisoformat(attempts['locked_until'])
        if datetime.datetime.now() < locked_until:
            remaining = (locked_until - datetime.datetime.now()).seconds
            if remaining >= 3600:
                hours = remaining // 3600
                return True, f'已锁定，请{hours}小时后再试'
            else:
                mins = remaining // 60
                return True, f'已锁定，请{mins}分钟后再试'
    return False, ''

def record_failed_login():
    attempts = get_failed_attempts()
    now = datetime.datetime.now()
    
    if attempts['first_fail_time']:
        first_fail = datetime.datetime.fromisoformat(attempts['first_fail_time'])
        if (now - first_fail).total_seconds() > 86400:
            attempts = {'count': 0, 'first_fail_time': None, 'locked_until': None}
    
    if attempts['count'] == 0:
        attempts['first_fail_time'] = now.isoformat()
    
    attempts['count'] += 1
    
    if attempts['count'] >= 10:
        locked_until = now + datetime.timedelta(days=1)
        attempts['locked_until'] = locked_until.isoformat()
    elif attempts['count'] >= 5:
        locked_until = now + datetime.timedelta(hours=1)
        attempts['locked_until'] = locked_until.isoformat()
    
    save_failed_attempts(attempts)

def clear_failed_attempts():
    attempts_file = os.path.join(PASSWORD_DIR, 'attempts')
    if os.path.exists(attempts_file):
        os.remove(attempts_file)

def verify_account(username, password):
    account_file = os.path.join(PASSWORD_DIR, 'account')
    if not os.path.exists(account_file):
        return False
    
    with open(account_file, 'r') as f:
        data = json.load(f)
    
    if data['username'] != username:
        return False
    
    return bcrypt.checkpw(password.encode(), data['password'].encode())

def is_logged_in():
    return session.get('logged_in', False)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def get_btrfs_partitions():
    result = subprocess.run(['blkid', '-t', 'TYPE=btrfs', '-o', 'device'], capture_output=True, text=True)
    partitions = []
    btrfs_mounts = []
    
    # 使用findmnt读取挂载信息，支持带空格的路径
    mount_result = subprocess.run(
        ['findmnt', '-t', 'btrfs', '-no', 'SOURCE,TARGET,OPTIONS'],
        capture_output=True, text=True
    )
    if mount_result.returncode == 0 and mount_result.stdout.strip():
        for line in mount_result.stdout.strip().split('\n'):
            # 去掉findmnt的树状符号
            line = line.replace('└─', '').replace('├─', '').strip()
            # SOURCE字段可能包含[子卷路径]，需要处理
            if '[' in line:
                dev_part = line[:line.index('[')].strip()
            else:
                dev_part = line.split()[0]
            # 提取TARGET挂载点：SOURCE后面的部分，到OPTIONS（包含subvol=）之前
            parts = line.split()
            target = ''
            subvol = '/'
            for i in range(1, len(parts)):
                if 'subvol=' in parts[i]:
                    # 找到subvol参数
                    for opt in parts[i].split(','):
                        if opt.startswith('subvol='):
                            subvol = opt.split('=', 1)[1]
                            break
                    break
                else:
                    # 拼接带空格的挂载路径
                    if target:
                        target += ' ' + parts[i]
                    else:
                        target = parts[i]
            if target:
                btrfs_mounts.append({'dev': dev_part, 'mount_point': target, 'subvol': subvol})
    
    if result.returncode == 0 and result.stdout.strip():
        for dev in result.stdout.strip().split('\n'):
            if dev:
                label_result = subprocess.run(['blkid', '-s', 'LABEL', '-o', 'value', dev], capture_output=True, text=True)
                base_label = label_result.stdout.strip() or dev
                # 同一个分区的多个挂载点都单独返回
                dev_mounts = [m for m in btrfs_mounts if m['dev'] == dev]
                if dev_mounts:
                    for m in dev_mounts:
                        subvol = m['subvol']
                        if subvol == '/':
                            label = f"{base_label} (根卷)"
                        else:
                            label = f"{base_label} (子卷: {subvol})"
                        partitions.append({
                            'device': dev, 
                            'label': label, 
                            'mount_point': m['mount_point'],
                            'subvol': subvol
                        })
                else:
                    # 没有挂载的分区
                    partitions.append({'device': dev, 'label': base_label, 'mount_point': '', 'subvol': ''})
    return partitions

def get_subvolumes(mount_point):
    result = subprocess.run(['btrfs', 'subvolume', 'list', '-o', mount_point], capture_output=True, text=True)
    subvolumes = []
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) >= 9:
                    path = parts[8]
                    if 'snapshots' not in path:
                        subvolumes.append({
                            'id': parts[1],
                            'path': path
                        })
    return subvolumes

def get_folders(mount_point, filter_snapshots='exclude'):
    folders = []
    if not os.path.exists(mount_point):
        return folders
    
    result = subprocess.run(['btrfs', 'subvolume', 'list', mount_point], capture_output=True, text=True)
    subvol_paths = set()
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) >= 9:
                    subvol_paths.add(parts[8])
    
    for item in os.listdir(mount_point):
        full_path = os.path.join(mount_point, item)
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            if item in subvol_paths:
                continue
            if filter_snapshots == 'exclude':
                if 'snapshots' not in item:
                    folders.append(item)
            elif filter_snapshots == 'include_only':
                if 'snapshots' in item:
                    folders.append(item)
            else:
                folders.append(item)
    folders.sort()
    return folders

import re

def get_snapshots(mount_point):
    result = subprocess.run(['btrfs', 'subvolume', 'list', mount_point], capture_output=True, text=True)
    snapshots = []
    
    snapshot_pattern = re.compile(r'.*[-_][0-9]{8}(_[0-9]{6})?$')
    
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) >= 9:
                    path = parts[8]
                    if snapshot_pattern.search(path):
                        snapshots.append({
                            'id': parts[1],
                            'path': path
                        })
    return snapshots

def create_snapshot(mount_point, source_subvol, folder, name, readonly=False):
    if source_subvol:
        source_path = os.path.join(mount_point, source_subvol)
    else:
        source_path = mount_point
    
    dest_path = os.path.join(mount_point, folder, name) if folder else os.path.join(mount_point, name)
    
    result = subprocess.run(['btrfs', 'subvolume', 'snapshot', source_path, dest_path], capture_output=True, text=True)
    if result.returncode == 0:
        if readonly:
            subprocess.run(['btrfs', 'property', 'set', dest_path, 'ro', 'true'], capture_output=True)
        return True, result.stdout
    return False, result.stderr

def delete_snapshot(mount_point, path):
    full_path = os.path.join(mount_point, path) if not path.startswith('/') else path
    result = subprocess.run(['btrfs', 'subvolume', 'delete', full_path], capture_output=True, text=True)
    return result.returncode == 0, result.stdout + result.stderr

def set_readonly(mount_point, path, readonly=True):
    full_path = os.path.join(mount_point, path) if not path.startswith('/') else path
    result = subprocess.run(['btrfs', 'property', 'set', full_path, 'ro', str(readonly).lower()], capture_output=True, text=True)
    return result.returncode == 0

def add_record(task_type, partition, snapshot_name, action, success, message):
    config = load_config()
    record = {
        'timestamp': datetime.datetime.now().isoformat(),
        'type': task_type,
        'partition': partition,
        'snapshot': snapshot_name,
        'action': action,
        'success': success,
        'message': message
    }
    if task_type == 'auto':
        config['auto_records'] = config.get('auto_records', [])
        config['auto_records'].append(record)
    else:
        config['manual_records'] = config.get('manual_records', [])
        config['manual_records'].append(record)
    save_config(config)
    clean_old_records()

def clean_old_records():
    config = load_config()
    max_mb = config.get('max_storage_mb', 100)
    
    for record_type in ['auto_records', 'manual_records']:
        records = config.get(record_type, [])
        total_size = sum(len(json.dumps(r).encode()) for r in records)
        
        while total_size > max_mb * 1024 * 1024 and records:
            records.pop(0)
            total_size = sum(len(json.dumps(r).encode()) for r in records)
        
        config[record_type] = records
    
    save_config(config)

def execute_auto_task(task_id):
    config = load_config()
    task = None
    for t in config.get('scheduled_tasks', []):
        if t['id'] == task_id:
            task = t
            break
    
    if not task:
        return
    
    mount_point = task.get('mount_point')
    if not mount_point:
        return
    
    name = f"{task['name']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    source_subvol = task.get('source_subvol', '')
    folder = task.get('folder', '')
    success, msg = create_snapshot(mount_point, source_subvol, folder, name, task.get('readonly', False))
    
    add_record('auto', task['partition'], name, 'create', success, msg)
    
    if success and task.get('update_latest', True):
        latest_link = os.path.join(mount_point, folder, f"{task['name']}_latest") if folder else os.path.join(mount_point, f"{task['name']}_latest")
        target_path = os.path.join(mount_point, folder, name) if folder else os.path.join(mount_point, name)
        if os.path.exists(target_path):
            try:
                if os.path.lexists(latest_link):
                    if os.path.islink(latest_link):
                        os.unlink(latest_link)
                    else:
                        if os.path.isdir(latest_link):
                            shutil.rmtree(latest_link)
                        else:
                            os.remove(latest_link)
                os.symlink(target_path, latest_link)
            except Exception as e:
                add_record('auto', task['partition'], name, 'create_latest_link', False, f"创建latest链接失败: {str(e)}")
    
    max_keep = task.get('max_keep')
    if max_keep and max_keep > 0:
        cleanup_old_snapshots(mount_point, max_keep)

def cleanup_old_snapshots(mount_point, max_keep):
    snapshots = get_snapshots(mount_point)
    snap_prefixes = {}
    
    for sv in snapshots:
        path = sv['path']
        # 取路径最后一级作为文件名
        filename = os.path.basename(path)
        for task in load_config().get('scheduled_tasks', []):
            if task['mount_point'] == mount_point:
                prefix = task['name']
                # 判断文件名是否以"任务名_"开头，确保匹配正确
                if filename.startswith(f"{prefix}_"):
                    if prefix not in snap_prefixes:
                        snap_prefixes[prefix] = []
                    snap_prefixes[prefix].append({'path': path, 'id': sv['id']})
    
    for prefix, snaps in snap_prefixes.items():
        snaps.sort(key=lambda x: x['path'], reverse=True)
        if len(snaps) > max_keep:
            for snap in snaps[max_keep:]:
                delete_snapshot(mount_point, snap['path'])

def setup_scheduler():
    config = load_config()
    scheduler.remove_all_jobs()
    
    for task in config.get('scheduled_tasks', []):
        if not task.get('enabled', True):
            continue
        
        trigger = None
        if task['schedule_type'] == 'daily':
            trigger = CronTrigger(
                hour=int(task['hour']),
                minute=int(task['minute']),
                second=int(task.get('second', 0))
            )
        elif task['schedule_type'] == 'weekly':
            trigger = CronTrigger(
                day_of_week=int(task['day_of_week']),
                hour=int(task['hour']),
                minute=int(task['minute']),
                second=int(task.get('second', 0))
            )
        elif task['schedule_type'] == 'monthly':
            trigger = CronTrigger(
                day=int(task['day']),
                hour=int(task['hour']),
                minute=int(task['minute']),
                second=int(task.get('second', 0))
            )
        
        if trigger:
            scheduler.add_job(
                lambda t=task['id']: execute_auto_task(t),
                trigger,
                id=str(task['id'])
            )
    
    if not scheduler.running:
        scheduler.start()

@app.route('/')
def index():
    if not has_account():
        return render_template('login.html', mode='create')
    if not is_logged_in():
        return render_template('login.html', mode='login')
    partitions = get_btrfs_partitions()
    partitions.sort(key=lambda x: x.get('label', ''))
    config = load_config()
    default_partition = partitions[0] if partitions else None
    default_subvolumes = []
    default_folders = []
    default_snapshots = []
    if default_partition and default_partition.get('mount_point'):
        default_subvolumes = get_subvolumes(default_partition['mount_point'])
        default_folders = get_folders(default_partition['mount_point'], filter_snapshots='include_only')
        default_snapshots = get_snapshots(default_partition['mount_point'])
    return render_template('index.html', partitions=partitions, config=config, default_partition=default_partition, default_subvolumes=default_subvolumes, default_folders=default_folders, default_snapshots=default_snapshots)

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not has_account():
        clear_failed_attempts()
        success, msg = create_account(username, password)
        if success:
            session['logged_in'] = True
            session['username'] = username
        return jsonify({'success': success, 'message': msg})
    
    locked, msg = check_locked()
    if locked:
        return jsonify({'success': False, 'message': msg})
    
    if verify_account(username, password):
        clear_failed_attempts()
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'success': True, 'message': '登录成功'})
    
    record_failed_login()
    attempts = get_failed_attempts()
    if attempts.get('locked_until'):
        return jsonify({'success': False, 'message': '密码错误次数过多，已锁定'})
    return jsonify({'success': False, 'message': '用户名或密码错误'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/api/check_account')
def api_check_account():
    return jsonify({'has_account': has_account()})

@app.route('/api/partitions')
def api_partitions():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    partitions = get_btrfs_partitions()
    return jsonify(partitions)

@app.route('/api/subvolumes')
def api_get_subvolumes():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    mount_point = request.args.get('mount_point', '')
    subvolumes = get_subvolumes(mount_point)
    return jsonify(subvolumes)

@app.route('/api/folders')
def api_folders():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    mount_point = request.args.get('mount_point', '')
    filter_snapshots = request.args.get('filter_snapshots', 'exclude')
    folders = get_folders(mount_point, filter_snapshots)
    return jsonify(folders)

@app.route('/api/snapshots')
def api_subvolumes():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    mount_point = request.args.get('mount_point', '')
    subvolumes = get_snapshots(mount_point)
    return jsonify(subvolumes)

@app.route('/api/snapshot', methods=['POST'])
def api_create_snapshot():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    data = request.json
    mount_point = data.get('mount_point')
    source_subvol = data.get('source_subvol', '')
    folder = data.get('folder', '')
    name = data.get('name')
    readonly = data.get('readonly', False)
    
    success, msg = create_snapshot(mount_point, source_subvol, folder, name, readonly)
    add_record('manual', mount_point, name, 'create', success, msg)
    
    return jsonify({'success': success, 'message': msg})

@app.route('/api/snapshot', methods=['DELETE'])
def api_delete_snapshot():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    data = request.json
    mount_point = data.get('mount_point')
    path = data.get('path')
    
    success, msg = delete_snapshot(mount_point, path)
    add_record('manual', mount_point, path, 'delete', success, msg)
    
    return jsonify({'success': success, 'message': msg})

@app.route('/api/set_readonly', methods=['POST'])
def api_set_readonly():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    data = request.json
    mount_point = data.get('mount_point')
    path = data.get('path')
    readonly = data.get('readonly', True)
    
    success = set_readonly(mount_point, path, readonly)
    return jsonify({'success': success})

@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    data = request.json
    config = load_config()
    
    task = {
        'id': int(datetime.datetime.now().timestamp()),
        'name': data.get('name'),
        'partition': data.get('partition'),
        'mount_point': data.get('mount_point'),
        'source_subvol': data.get('source_subvol', ''),
        'folder': data.get('folder', ''),
        'schedule_type': data.get('schedule_type'),
        'hour': data.get('hour', 0),
        'minute': data.get('minute', 0),
        'second': data.get('second', 0),
        'day_of_week': data.get('day_of_week', 0),
        'day': data.get('day', 1),
        'readonly': data.get('readonly', False),
        'max_keep': data.get('max_keep', 0),
        'update_latest': data.get('update_latest', True),
        'enabled': True
    }
    
    config['scheduled_tasks'] = config.get('scheduled_tasks', [])
    config['scheduled_tasks'].append(task)
    save_config(config)
    setup_scheduler()
    
    return jsonify({'success': True})

@app.route('/api/schedule/<int:task_id>', methods=['DELETE'])
def api_delete_schedule(task_id):
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    config = load_config()
    config['scheduled_tasks'] = [t for t in config.get('scheduled_tasks', []) if t['id'] != task_id]
    save_config(config)
    setup_scheduler()
    
    return jsonify({'success': True})

@app.route('/api/schedule/<int:task_id>/toggle', methods=['POST'])
def api_toggle_schedule(task_id):
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    config = load_config()
    for task in config.get('scheduled_tasks', []):
        if task['id'] == task_id:
            task['enabled'] = not task.get('enabled', True)
            break
    save_config(config)
    setup_scheduler()
    
    return jsonify({'success': True})

@app.route('/api/records')
def api_records():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    config = load_config()
    record_type = request.args.get('type', 'all')
    date_range = request.args.get('date_range', 'all')
    
    records = []
    if record_type in ['all', 'auto']:
        records.extend(config.get('auto_records', []))
    if record_type in ['all', 'manual']:
        records.extend(config.get('manual_records', []))
    
    if date_range != 'all':
        now = datetime.datetime.now()
        if date_range == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == 'week':
            start = now - datetime.timedelta(days=7)
        elif date_range == 'month':
            start = now - datetime.timedelta(days=30)
        elif date_range == 'year':
            start = now - datetime.timedelta(days=365)
        elif date_range == 'custom':
            custom_date = request.args.get('custom_date')
            if custom_date:
                start = datetime.datetime.strptime(custom_date, '%Y-%m-%d')
            else:
                start = None
        
        if start:
            records = [r for r in records if datetime.datetime.fromisoformat(r['timestamp']) >= start]
    
    records.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(records)

@app.route('/api/config', methods=['POST'])
def api_config():
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    data = request.json
    config = load_config()
    config['max_storage_mb'] = data.get('max_storage_mb', 100)
    save_config(config)
    clean_old_records()
    
    return jsonify({'success': True})

@app.route('/api/run_now/<int:task_id>')
def api_run_now(task_id):
    if not is_logged_in():
        return jsonify({'error': '未登录'}), 401
    execute_auto_task(task_id)
    return jsonify({'success': True})

if __name__ == '__main__':
    setup_scheduler()
    app.run(host='0.0.0.0', port=5003, debug=False)
