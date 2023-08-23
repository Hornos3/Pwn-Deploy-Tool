import os
import hashlib
import subprocess
import zipfile
from colorama import Fore
from util import *


class PdtImage:
    def __init__(self, name: str):
        self.name: str = name
        self.image = None
        self.apt: set[str] = {'xinetd', 'lib32z1', 'zip'}
        self.deploy: PdtDeploy = PdtDeploy()
        self._port: int = 0  # port of container itself, you can set outer ports for containers to map it to the host
        # runtime related
        self.image_id: str = ''
        self.status: str = 'unallocated'  # unallocated, built
        self.containers: dict[int, PdtContainer] = {}

    def initialize(self, info: dict):
        if {'image', 'apt list', 'base directory', 'deployed files',
            'entry file', 'port', 'image id', 'status', 'containers'} \
                < set(info.keys()):
            self.image = info['image']
            self.apt = info['apt list']
            self.deploy.basedir = info['base directory']
            self.deploy.files = info['deployed files']
            self.deploy.entry = info['entry file']
            self.port = info['port']
            self.image_id = info['image id']
            self.status = info['status']
            for c in info['containers']:
                container = PdtContainer(self)
                container.id = c
                container.status = info['containers'][c]['status']
                container.flag = info['containers'][c]['flag']
                container.outer_port = info['containers'][c]['mapping port']
                self.containers[c] = container
        else:
            PrettyPrinter.error(f'initialization of container {self.name} failed.')

    @property
    def info_dict(self):
        return {
            'name': self.name,
            'image': self.image if self.image is not None else '<not set>',
            'apt list': self.apt,
            'base directory': self.deploy.basedir if self.deploy.basedir != '' else '<not set>',
            'deployed files': self.deploy.files if len(self.deploy.files) != 0 else '<not set>',
            'entry file': self.deploy.entry if self.deploy.entry != '' else '<not set>',
            'port': self.port if self.port != 0 else '<not set>',
            'image id': self.image_id if self.image_id != '' else '<not set>',
            'status': Fore.RED + self.status if self.status == 'unallocated'
            else Fore.YELLOW + self.status if self.status == 'exited'
            else Fore.GREEN + self.status,
            'containers': {c.id: {
                'flag': c.flag if c.flag != '' else '<not set>',
                'mapping port': c.outer_port if c.outer_port != 0 else '<not set>',
                'status': Fore.RED + c.status if c.status == 'exited'
                else Fore.GREEN + c.status
            } for c in self.containers.values()}
        }

    @property
    def info_dict_for_config(self):
        return {
            'name': self.name,
            'image': self.image,
            'apt list': self.apt,
            'base directory': self.deploy.basedir,
            'deployed files': self.deploy.files,
            'entry file': self.deploy.entry,
            'port': self.port,
            'image id': self.image_id,
            'status': self.status,
            'containers': {c.id: {
                'flag': c.flag,
                'mapping port': c.outer_port,
                'status': c.status
            } for c in self.containers.values()}
        }

    '''****************************** getters and setters with checks ******************************'''

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        if not 1000 < value < 65536:
            PrettyPrinter.error('Port input is not a valid integer.')
            return
        self._port = value

    def build(self):
        if self.image is None or len(self.deploy.files) == 0 or self.deploy.entry == '' or self.port == 0:
            PrettyPrinter.error('Incomplete info of container found, use \'list\' to check the missing config.')
            PrettyPrinter.error('Failed to run ' + self.name)
            return
        with open('./templates/dockerfile.template', 'r') as f:
            dockerfile = f.read()
        with open('./templates/xinetd.template', 'r') as f:
            xinetd = f.read()
        if not os.path.exists(f'{DEPLOY_FILE_DIR}/{self.name}'):
            os.mkdir(f'{DEPLOY_FILE_DIR}/{self.name}')
        if not os.path.exists(f'{ZIP_DIR}/{self.deploy.hash()}.zip'):
            zf = zipfile.ZipFile(f'{ZIP_DIR}/{self.deploy.hash()}.zip', mode='w')
            PrettyPrinter.info(f'building {zf.filename} ...')
            for file in self.deploy.files:
                if os.path.isdir(f'{self.deploy.basedir}/{file}'):
                    for parent, dirname, filename in os.walk(f'{self.deploy.basedir}/{file}'):
                        for dirfile in filename:
                            PrettyPrinter.info(f'Adding {dirfile} ...')
                            zf.write(f'{parent}/{dirfile}', f'{parent}/{dirfile}'[len(self.deploy.basedir) + 1:])
                elif os.path.exists(f'{self.deploy.basedir}/{file}'):
                    zf.write(f'{self.deploy.basedir}/{file}', file)
                else:
                    PrettyPrinter.error(f'File not found: {self.deploy.basedir}/{file}')
            zf.close()

        # generate dockerfile
        d = open(f'{DEPLOY_FILE_DIR}/{self.name}/Dockerfile', 'w')
        d.write(
            dockerfile.format(
                image=self.image,
                apt=' '.join(list(self.apt)),
                copyfile=f'{self.deploy.hash()}.zip',
                entry=self.deploy.entry,
                basedir_in_docker=BASEDIR_IN_DOCKER,
                port=self.port,
                name=self.name
            )
        )
        d.close()

        # generate xinetd config file
        x = open(f'{DEPLOY_FILE_DIR}/{self.name}/pwn.xinetd', 'w')
        x.write(
            xinetd.replace('{**port**}', str(self.port))
            .replace('{**entry**}', f'{BASEDIR_IN_DOCKER}/{self.deploy.entry}')
        )
        x.close()

        # start service file
        os.system(f'cp ./templates/service.template ./runtime/deploy_files/{self.name}/service.sh')

        # build your image for pwn problems
        with open('./templates/build_shell.template', 'r') as f:
            shell = f.read()
        shell = shell.format(name=self.name, dockerfile=self.name+'/Dockerfile')
        with open(f'./runtime/deploy_files/{self.name}/build.sh', 'w') as f:
            f.write(shell)
        os.chmod(f'./runtime/deploy_files/{self.name}/build.sh', 0o744)
        return_code = os.system(f'./runtime/deploy_files/{self.name}/build.sh')
        if return_code == 0:
            PrettyPrinter.info(f'Successfully built image: {self.name}.')
            image_chart = analyse_console_table(
                subprocess.Popen('docker images', shell=True, stdout=subprocess.PIPE).stdout.read().decode())
            image_id = image_chart.loc[image_chart.REPOSITORY == self.name, 'IMAGE ID']
            if len(image_id) == 1:
                self.image_id = image_id[0]
            else:
                PrettyPrinter.error('It seems that the docker successfully built the image, but not found.')
                return
            self.status = 'built'
        else:
            PrettyPrinter.error(f'Failed to build image: {self.name}')

    def next_container_id(self):
        return len(self.containers) + 1


class PdtDeploy:
    def __init__(self):
        self.basedir = ''
        self.files: set = set([])
        self.entry = ''

    def hash(self):
        return hashlib.sha256((str(self.basedir) + ";" + str(self.files) + ';' + self.entry).encode()).hexdigest()

    @property
    def basedir(self):
        return self._basedir

    @basedir.setter
    def basedir(self, value):
        newone = relative_to_absolute_path(value)
        if newone is not None and os.path.isdir(newone):
            self._basedir = newone
        elif not os.path.isdir(newone):
            PrettyPrinter.error('Failed to set base directory: target is a file.')
        else:
            PrettyPrinter.error('Failed to set base directory: directory not found.')


class PdtContainer:
    def __init__(self, image: PdtImage):
        self.image: PdtImage = image
        self.flag = ''
        self.outer_port = 0  # used for mapping container's port into host
        self.status = 'exited'  # exited, running
        self.id = 0
        self.container_id = ''

    def run(self, outer_port: int, flag: str):
        pass
