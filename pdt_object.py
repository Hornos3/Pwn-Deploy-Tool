import docker
import hashlib
import zipfile
from util import *
from docker import errors
from docker.client import DockerClient
from docker.models.containers import Container
from docker.models.images import Image


class PdtImage:
    def __init__(self, name: str, docker_client: docker.client.DockerClient):
        self.__name: str = name
        self.__parent: Image | None = None          # image object of docker SDK
        self.__image_object: Image | None = None  # image object of docker SDK
        self.apt: set[str] = {'xinetd', 'lib32z1', 'zip'}
        self.deploy: PdtDeploy = PdtDeploy()
        self._port: int = 0  # port of container itself, you can set outer ports for __containers to map it to the host
        # runtime related
        self.__docker_client: DockerClient = docker_client
        self.__containers: dict[int, PdtContainer] = {}

    def initialize(self, info: dict):
        if {'name', 'parent image id', 'apt list', 'base directory', 'deployed files',
            'entry file', 'port', 'containers'} \
                < set(info.keys()):
            self.__name = info['name']
            try:
                self.__parent = self.__docker_client.images.get(info['parent image id']) \
                    if info['parent image id'] is not None else None
            except docker.errors.ImageNotFound:
                PrettyPrinter.error(f"parent image for {info['name']}({info['parent image id']} not found.)")
                self.__parent = None
            try:
                self.__parent = self.__docker_client.images.get(info['image id']) \
                    if info['image id'] is not None else None
            except docker.errors.ImageNotFound:
                PrettyPrinter.error(f"image id {info['image id']} not found.")
                self.__image_object = None
            self.apt = info['apt list']
            self.deploy.basedir = info['base directory']
            self.deploy.files = info['deployed files']
            self.deploy.entry = info['entry file']
            self.port = info['port']
            idx = 1
            for c in info['containers'].keys():
                try:        # discard containers not found
                    container_object = self.__docker_client.containers.get(info['containers'][c]['container id'])
                except docker.errors.NotFound:
                    PrettyPrinter.error(f"container {info['containers'][c]['container id']} not found.")
                    continue
                container = PdtContainer(self)
                container.id = idx
                container.flag = info['containers'][c]['flag']
                container.outer_port = info['containers'][c]['mapping port']
                container.container_object = container_object
                self.__containers[idx] = container
                idx += 1
        else:
            PrettyPrinter.error(f'initialization of container {self.__name} failed.')

    @property
    def info_dict(self):
        return {
            'name': self.__name,
            'parent image id': self.parent_image_id,
            'image id': self.image_id,
            'apt list': self.apt,
            'base directory': self.deploy.basedir if self.deploy.basedir != '' else '<not set>',
            'deployed files': self.deploy.files if len(self.deploy.files) != 0 else '<not set>',
            'entry file': self.deploy.entry if self.deploy.entry != '' else '<not set>',
            'port': self.port if self.port != 0 else '<not set>',
            'containers': {c.id: {
                'flag': c.flag if c.flag != '' else '<not set>',
                'mapping port': c.outer_port if c.outer_port != 0 else '<not set>',
                'container id': c.container_id
            } for c in self.__containers.values()}
        }

    @property
    def info_dict_for_config(self):
        return {
            'name': self.__name,
            'parent image id': self.parent_image_id,
            'image id': self.image_id,
            'apt list': self.apt,
            'base directory': self.deploy.basedir,
            'deployed files': self.deploy.files,
            'entry file': self.deploy.entry,
            'port': self.port,
            'containers': {c.id: {
                'flag': c.flag,
                'mapping port': c.outer_port,
                'container id': c.container_id
            } for c in self.__containers.values()}
        }

    @property
    def name(self):
        return self.__name

    @property
    def parent_image_id(self):
        return self.__parent.short_id[7:] if self.__parent is not None else None

    @property
    def parent(self):
        return self.__parent

    @parent.setter
    def parent(self, name: str):
        try:
            self.__parent = self.__docker_client.images.get(name)
        except docker.errors.ImageNotFound:
            PrettyPrinter.error(f"Image {name} not found in your host machine, please download it first.")

    @property
    def parent_image_object(self):
        return self.__parent

    @property
    def image_id(self):
        return self.__image_object.short_id[7:] if self.__image_object is not None else None

    @property
    def image_object(self):
        return self.__image_object

    @property
    def containers(self):
        return self.__containers

    @property
    def container_cnt(self):
        return len(self.__containers.keys())

    def container_stat(self, idx: int):
        if 1 <= idx <= len(self.__containers.keys()):
            return self.__containers[idx].container_object.status
        PrettyPrinter.error(f"Index out of bound for getting status of container #{idx}")

    def start_container(self, idx: int):
        if 1 <= idx <= len(self.__containers.keys()):
            self.__containers[idx].container_object.start()
        else:
            PrettyPrinter.error(f"Index out of bound for starting a container #{idx}")

    '''****************************** getters and setters with checks ******************************'''

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        if not 10000 < value < 65536:
            PrettyPrinter.error('Port input is not a valid integer.')
            return
        self._port = value

    def build(self):
        if self.__parent is None or len(self.deploy.files) == 0 or self.deploy.entry == '' or self.port == 0:
            PrettyPrinter.error('Incomplete info of container found, use \'list\' to check the missing config.')
            PrettyPrinter.error('Failed to run ' + self.__name)
            return
        with open('./templates/dockerfile.template', 'r') as f:
            dockerfile = f.read()
        with open('./templates/xinetd.template', 'r') as f:
            xinetd = f.read()
        if not os.path.exists(f'{DEPLOY_FILE_DIR}/{self.__name}'):
            os.mkdir(f'{DEPLOY_FILE_DIR}/{self.__name}')
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
        d = open(f'{DEPLOY_FILE_DIR}/{self.__name}/Dockerfile', 'w')
        d.write(
            dockerfile.format(
                image=self.__parent.tags[0],
                apt=' '.join(list(self.apt)),
                copyfile=f'{self.deploy.hash()}.zip',
                entry=self.deploy.entry,
                basedir_in_docker=BASEDIR_IN_DOCKER,
                port=self.port,
                name=self.__name
            )
        )
        d.close()

        # generate xinetd config file
        x = open(f'{DEPLOY_FILE_DIR}/{self.__name}/pwn.xinetd', 'w')
        x.write(
            xinetd.replace('{**port**}', str(self.port))
            .replace('{**entry**}', f'{BASEDIR_IN_DOCKER}/{self.deploy.entry}')
        )
        x.close()

        # start service file
        os.system(f'cp ./templates/service.template ./runtime/deploy_files/{self.__name}/service.sh')

        # # build your image for pwn problems
        # with open('./templates/build_shell.template', 'r') as f:
        #     shell = f.read()
        # shell = shell.format(name=self.__name, dockerfile=self.__name + '/Dockerfile')
        # with open(f'./runtime/deploy_files/{self.__name}/build.sh', 'w') as f:
        #     f.write(shell)
        # os.chmod(f'./runtime/deploy_files/{self.__name}/build.sh', 0o744)

        try:
            self.__image_object, _ = self.__docker_client.images.build(
                path=relative_to_absolute_path('./runtime/deploy_files'),
                tag=self.__name,
                dockerfile=relative_to_absolute_path(f'runtime/deploy_files/{self.__name}/Dockerfile'),
                quiet=False,
                rm=True
            )
        except docker.errors.BuildError:
            PrettyPrinter.error(f'Failed to build image: {self.__name}')
            return
        PrettyPrinter.info(f'Successfully built image: {self.__name}.')

        # return_code = os.system(f'./runtime/deploy_files/{self.__name}/build.sh')
        # if return_code == 0:
        #     PrettyPrinter.info(f'Successfully built image: {self.__name}.')
        # else:
        #     PrettyPrinter.error(f'Failed to build image: {self.__name}')

    def next_container_id(self):
        return len(self.__containers) + 1

    def add_container(self, outer_port: None | int = None, flag: None | str = None, exit_after_created: bool = False):
        new_container: PdtContainer = PdtContainer(self)
        new_container.id = self.next_container_id()
        if outer_port is not None:
            if not 10000 <= outer_port <= 65535:
                PrettyPrinter.warning(f"Bad outer port specified: {outer_port}, 10000~65535 needed.")
                new_container.outer_port = get_free_port()
                PrettyPrinter.info(f"Allocated a random free port: {new_container.outer_port}")
            else:
                if check_sock_free(outer_port):
                    new_container.outer_port = outer_port
                else:
                    PrettyPrinter.warning(f"Specified port was occupied.")
                    new_container.outer_port = get_free_port()
                    PrettyPrinter.info(f"Allocated a random free port: {new_container.outer_port}")
        else:
            new_container.outer_port = get_free_port()
            PrettyPrinter.info(f"Allocated a random free port: {new_container.outer_port}")
        if flag is not None:
            new_container.flag = flag
        while True:
            try:
                new_container.container_object = self.__docker_client.containers.run(
                    image=self.__name,
                    ports={f'{self.port}/tcp': ('0.0.0.0', new_container.outer_port)},
                    detach=True
                )
                break
            except docker.errors.APIError:
                PrettyPrinter.warning("Socket seized. Trying to get a new port...")
                new_container.outer_port = get_free_port()

        if exit_after_created:
            new_container.container_object.stop()
        PrettyPrinter.info(f'Successfully created a container, id={new_container.id},'
                           f' container_id={new_container.container_id}')
        self.__containers[new_container.id] = new_container

    def delete_all_containers(self):
        if self.container_cnt == 0:
            return
        for _, ctn in self.__containers.items():
            if ctn.container_object.status in ('running', 'created'):
                ctn.container_object.stop()
            ctn.container_object.remove()
        self.__containers.clear()
        PrettyPrinter.info(f"All containers of {self.__name} deleted.")

    def __delete_a_container(self, cid: int):
        # This method do not include rearrangement of ids
        ctn = next((c for c in self.__containers.values() if c.id == cid), None)
        if ctn is None:
            PrettyPrinter.error(f'container for id {cid} not found.')
            return
        if str(ctn.container_object.status) in ('running', 'created'):
            ctn.container_object.stop()
        ctn.container_object.remove()
        del self.__containers[cid]
        PrettyPrinter.info(f"Container {cid} of {self.__name} deleted.")

    def delete_containers(self, cid: list):
        """
        delete __containers for selected ranges
        :param cid: list of ids, each element is a range needed to be deleted, like [1, 5] means id 1-5.
        :return: None
        """
        for item in cid:
            start = item[0]
            end = item[1]
            if not self.check_cid_range(start, end):
                return
            for i in range(start, end + 1):
                self.__delete_a_container(i)
        self.__rearrange_id()

    def __stop_a_container(self, cid: int) -> None:
        ctn = next((c for c in self.__containers.values() if c.id == cid), None)
        if ctn is None:
            PrettyPrinter.error(f'container for id {cid} not found.')
            return
        if ctn.container_object.status in ('created', 'running'):
            ctn.container_object.stop()
            PrettyPrinter.info(f"Container {cid} of {self.__name} stopped.")

    def stop_containers(self, cid: list) -> None:
        for item in cid:
            start = item[0]
            end = item[1]
            if not self.check_cid_range(start, end):
                return
            for i in range(start, end + 1):
                self.__stop_a_container(i)

    def __rearrange_id(self) -> None:
        sorted_keys = sorted(self.__containers.keys())
        new_dict = {}
        for index, key in enumerate(sorted_keys, start=1):
            new_dict[index] = self.__containers[key]
            new_dict[index].id = index
        self.__containers = new_dict

    @staticmethod
    def check_cid_range(start, end):
        if start > end:
            PrettyPrinter.error(f'format error, range start cannot be larger than range end: {start}-{end}')
            return False
        if start <= 0 or end <= 0:
            PrettyPrinter.error(f'format error, range start and end can only be positive: {start}-{end}')
            return False
        return True

    def delete_image(self):
        if self.__image_object is not None:
            self.__image_object.remove()
        PrettyPrinter.info(f"Successfully deleted image {self.__name}")


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
        self.flag: str = ''
        self.outer_port: int = 0  # used for mapping container's port into host
        self.id: int = 0
        self.container_object: Container | None = None

    @property
    def container_id(self):
        if self.container_object is not None:
            return self.container_object.short_id
        return None

    @property
    def status(self):
        if self.container_object is not None:
            return self.container_object.status
        return None

    def run(self, outer_port: int, flag: str):
        pass
