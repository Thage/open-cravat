from bottle import app, route, get, post, request, response, run, static_file
import os
import time
import datetime
import subprocess
import yaml
import json

class FileRouter(object):

    def __init__(self):
        self.root = os.path.dirname(__file__)

    def static_dir(self):
        return os.path.join(self.root, 'static')

    def jobs_dir(self):
        return os.path.join(self.root, 'jobs')

    def job_dir(self, job_id):
        return os.path.join(self.jobs_dir(), job_id)

    def job_info_file(self, job_id):
        info_fname = '{}.info.yaml'.format(job_id)
        return os.path.join(self.job_dir(job_id), info_fname)

    def job_input_file(self, job_id):
        input_fname = 'input'
        return os.path.join(self.job_dir(job_id), input_fname)

    def job_output_db(self, job_id):
        output_fname = 'input.sqlite'
        return os.path.join(self.job_dir(job_id), output_fname)

class WebJob(object):
    def __init__(self, job_dir, job_info_fpath):
        self.job_dir = job_dir
        self.job_info_fpath = job_info_fpath
        self.info = JobInfo(id=os.path.basename(job_dir))

    def read_info_file(self):
        with open(self.job_info_fpath) as f:
            info_dict = yaml.load(f)
        self.info.set_values(**info_dict)

    def set_info_values(self, **kwargs):
        self.info.set_values(**kwargs)

    def write_info_file(self):
        with open(self.job_info_fpath,'w') as wf:
            yaml.dump(self.get_info_dict(), wf, default_flow_style=False)
    
    def get_db_path(self):
        return os.path.join(self.job_dir, self.info.output_db)

    def get_info_dict(self):
        return vars(self.info)

class JobInfo(object):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_ERROR = 'error'
    STATUS_COMPLETE = 'complete'

    def __init__(self, **kwargs):
        self.set_values(**kwargs)
        
    def set_values(self, **kwargs):
        all_vars = vars(self)
        all_vars.update(kwargs)
        self.orig_input_fname = all_vars.get('orig_input_fname')
        self.submission_time = all_vars.get('submission_time')
        self.start_time = all_vars.get('start_time')
        self.stop_time = all_vars.get('stop_time')
        self.id = all_vars.get('id')
        self.status = all_vars.get('status')

FILE_ROUTER = FileRouter()
VIEW_PROCESS = None
RUN_PROCESS = None

def get_next_job_id():
    return datetime.datetime.now().strftime(r'job-%Y-%m-%d-%H-%M-%S')

@post('/rest/submit')
def submit():
    global FILE_ROUTER
    global RUN_PROCESS
    file_formpart = request.files.get('file')
    orig_input_fname = file_formpart.raw_filename
    job_id = get_next_job_id()
    job_dir = FILE_ROUTER.job_dir(job_id)
    job_info_fpath = FILE_ROUTER.job_info_file(job_id)
    os.mkdir(job_dir)
    job = WebJob(job_dir, job_info_fpath)
    input_fpath = os.path.join(job_dir, FILE_ROUTER.job_input_file(job_id))
    with open(input_fpath,'wb') as wf:
        wf.write(file_formpart.file.read())
    job.set_info_values(orig_input_fname=orig_input_fname,
                        status=JobInfo.STATUS_QUEUED,
                        submission_time=time.time())
    job.write_info_file()
    job.set_info_values(start_time=time.time(),
                        status=JobInfo.STATUS_RUNNING)
    job.write_info_file()
    RUN_PROCESS = subprocess.run(['cravat', input_fpath])
    job.set_info_values(stop_time=time.time())
    if RUN_PROCESS.returncode == 0:
        job.set_info_values(status=JobInfo.STATUS_COMPLETE)
    else:
        job.set_info_values(status=JobInfo.STATUS_ERROR)
    job.write_info_file()
    return job.get_info_dict()

@get('/rest/jobs')
def get_all_jobs():
    global FILE_ROUTER
    ids = os.listdir(FILE_ROUTER.jobs_dir())
    all_jobs = []
    for job_id in ids:
        job_dir = FILE_ROUTER.job_dir(job_id)
        job_info_fpath = FILE_ROUTER.job_info_file(job_id)
        job = WebJob(job_dir, job_info_fpath)
        job.read_info_file()
        all_jobs.append(job)
    response.content_type = 'application/json'
    return json.dumps([job.get_info_dict() for job in all_jobs])

@post('/rest/view')
def view():
    global VIEW_PROCESS
    global FILE_ROUTER
    job_id = request.json['jobId']
    db_path = FILE_ROUTER.job_output_db(job_id)
    if os.path.exists(db_path):
        if type(VIEW_PROCESS) == subprocess.Popen:
            VIEW_PROCESS.kill()
        VIEW_PROCESS = subprocess.Popen(['cravat-view', db_path])
            
@get('/static/<filepath:path>')
def static(filepath):
    return static_file(filepath, root=FILE_ROUTER.static_dir())

if __name__ == '__main__':
    run(host='localhost', port=8080, debug=True)