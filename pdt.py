import sys
import signal
import os.path
from pdt_object import *


class PdtFactory:
    def __init__(self, images):
        self.__docker_client = docker.from_env()
        self.__docker_images: list = []
        self.__docker_containers: list = []
        self.__images: list[PdtImage] = []
        if images is not None:
            for i in images:
                new_container = PdtImage(i['name'], self.__docker_client)
                new_container.initialize(i)
                self.__images.append(new_container)
        self.__selected_image: PdtImage = PdtImage('none', self.__docker_client)
        self.peek_docker_images()
        self.__command_tree = {
            'new': self.__new,
            'select': self.__select,
            'set': {
                'image': self.__set_parent,
                'apt': self.__set_apt,
                'basedir': self.__set_basedir,
                'deploy': self.__set_deploy,
                'entry': self.__set_entry,
                'port': self.__set_port
            },
            'list': {
                'image': self.__list_image,
                'apt': self.__list_apt,
                'deploy': self.__list_deploy,
                'select': self.__list_select,
                'status': self.__list_status
            },
            'build': self.__build,
            'run': self.__run,
            'rm': {
                'image': self.__rm_image,
                'container': self.__rm_container
            }
        }
        self.__arg_parser = argparse.ArgumentParser()
        self.__initialize_parsers()

    def __initialize_parsers(self):
        subparsers = self.__arg_parser.add_subparsers()

        # new
        parser_new = subparsers.add_parser(
            'new',
            help="Create docker object(s) not configured. You need to"
                 "use 'select' command to select one of them.")
        parser_new.add_argument('name', nargs='+', help='Image name to be created')
        parser_new.set_defaults(func=self.__new)

        # select
        parser_select = subparsers.add_parser(
            'select',
            help="Select one object that is ready to be configured."
                 "You can only select ONE object simultaneously.")
        parser_select.add_argument('name', type=str, action='store', help='Image you want to select')
        parser_select.set_defaults(func=self.__select)

        # set
        parser_set = subparsers.add_parser(
            'set',
            help="Set some config for the selected object.")
        subparsers_set = parser_set.add_subparsers()
        # set parent
        parser_set_parent = subparsers_set.add_parser(
            'parent',
            help="set the image you problem based on. The image must exist"
                 "in your host. Eg: set image ubuntu:20.04")
        parser_set_parent.add_argument('tag', type=str, action='store', help='Image tag')
        parser_set_parent.set_defaults(func=self.__set_parent)
        # set apt
        parser_set_apt = subparsers_set.add_parser(
            'apt',
            help='set the package name that your problem needs to install.'
                 'There are some packages installed in default, like xinetd.'
                 'Eg. set apt -a musl -r vim'
        )
        parser_set_apt.add_argument('-a', action='append', help='add packets')
        parser_set_apt.add_argument('-r', action='append', help='remove packets')
        parser_set_apt.set_defaults(func=self.__set_apt)
        # set basedir
        parser_set_basedir = subparsers_set.add_parser(
            'basedir',
            help='set the base directory of your problem. The basedir '
                 'must be a local path. In PDT, when you need to build a problem, '
                 'the PDT will zip your files into a .zip file, and the basedir '
                 'will influence the zip process. Eg. if you set basedir to /foo, '
                 'then when you need to zip /foo/1/1.txt and /foo/2.txt, then you '
                 'can get a zip file. If you unzip it, you can get 1/1.txt and 2.txt '
                 'in the directory where you place the zip file.'
        )
        parser_set_basedir.add_argument('base', type=str, action='store', help='base directory')
        parser_set_basedir.set_defaults(func=self.__set_basedir)
        # set deploy
        parser_set_deploy = subparsers_set.add_parser(
            'deploy',
            help='set the file you want to deploy in your problem. '
                 'Eg. set deploy -a cpp pwn.elf -r .gdb_history'
        )
        parser_set_deploy.add_argument('-a', action='append', help='add files/directories')
        parser_set_deploy.add_argument('-r', action='append', help='remove files/directories')
        parser_set_deploy.set_defaults(func=self.__set_deploy)
        # set entry
        parser_set_entry = subparsers_set.add_parser(
            'entry',
            help='set the entry file of your problem, this file must be '
                 'an executable file for Linux, like a shell file or an ELF file.'
        )
        parser_set_entry.add_argument('entry', type=str, action='store', help='entry file')
        parser_set_entry.set_defaults(func=self.__set_entry)
        # set port
        parser_set_port = subparsers_set.add_parser(
            'port',
            help='set the outer port of your problem '
        )
        parser_set_port.add_argument('port', type=int, choices=range(0, 65536), help='port specified')
        parser_set_port.set_defaults(func=self.__set_port)

        # list
        parser_list = subparsers.add_parser(
            'list',
            help='List some configs of selected objects.'
        )
        subparsers_list = parser_list.add_subparsers()
        # list image
        parser_list_image = subparsers_list.add_parser(
            'image',
            help='Show the images managed by pdt.'
        )
        parser_list_image.add_argument('image', nargs='*', type=str, action='store', help='Image specified')
        parser_list_image.add_argument('-d', action='store_true', help='Show detailed information')
        parser_list_image.add_argument('-a', action='store_true', help='Show all images')
        parser_list_image.set_defaults(func=self.__list_image)
        # list apt
        parser_list_apt = subparsers_list.add_parser(
            'apt',
            help='Show the apt packages should be installed.'
        )
        parser_list_apt.add_argument('-a', action='store_true', help='Show all the images')
        parser_list_apt.set_defaults(func=self.__list_apt)
        # list deploy
        parser_list_deploy = subparsers_list.add_parser(
            'deploy',
            help='Show the file deployed in selected objects.'
        )
        parser_list_deploy.add_argument('-a', action='store_true', help='Show all the images')
        parser_list_deploy.set_defaults(func=self.__list_deploy)
        # list select
        parser_list_select = subparsers_list.add_parser(
            'select',
            help='Show the selected image.'
        )
        parser_list_select.add_argument('-d', action='store_true', help='Show detailed information')
        parser_list_select.set_defaults(func=self.__list_select)

        # build
        parser_build = subparsers.add_parser(
            'build',
            help='Start building selected image. You will get an image for '
                 'your problem, you need to use \'run\' to create __containers.'
        )
        parser_build.set_defaults(func=self.__build)

        # run
        parser_run = subparsers.add_parser(
            'run',
            help='Create/Start __containers for your problem.'
        )
        parser_run.add_argument('ids', type=lambda v: validate_ids(v), nargs='*', action='append')
        parser_run.add_argument('-n', type=int, action='store', help='Create new container(s)')
        parser_run.add_argument('-p', type=int, choices=range(0, 65536), action='store',
                                help='Set outer port(s), if not specified, PDT will select free ports randomly')
        parser_run.add_argument('-f', action='store',
                                help='Set the flag, if not specified, the flag will be randomly generated')
        parser_run.add_argument('-a', action='store_true', help='Start all __containers')
        parser_run.set_defaults(func=self.__run)

        # rm
        parser_rm = subparsers.add_parser(
            'rm',
            help='Remove something.'
        )
        subparsers_rm = parser_rm.add_subparsers()
        # rm image
        parser_rm_image = subparsers_rm.add_parser(
            'image',
            help='Remove some image(s). '
                 'If both -y and -n are not specified, PDT will ask you whether images with '
                 'existing containers should be deleted.'
        )
        parser_rm_image.add_argument('images', nargs='+', help='images needed to be deleted')
        parser_rm_image.add_argument('-y', action='store_true',
                                     help='If there are existing containers of images to be removed, '
                                          'PDT will delete these containers first, and delete the image.')
        parser_rm_image.add_argument('-n', action='store_true',
                                     help='If there are existing containers of images to be removed, '
                                          'PDT will not delete these containers and images.')
        parser_rm_image.set_defaults(func=self.__rm_image)
        # rm container
        parser_rm_container = subparsers_rm.add_parser(
            'container',
            help='Remove some container(s). '
                 'Argument format: '
                 '"rm container foo.1,4-5,6-12 goo.2-10" --- '
                 'It means deleting the container 1, 4~5, 6~12 of image foo, and container '
                 '2~10 of image goo.'
        )
        parser_rm_container.add_argument('containers', nargs='+', help='containers needed to be deleted')
        parser_rm_container.set_defaults(func=self.__rm_container)

        # stop
        parser_stop = subparsers.add_parser(
            'stop',
            help='Stop something(containers supported only until now).'
        )
        subparsers_stop = parser_stop.add_subparsers()
        # stop container
        parser_stop_container = subparsers_stop.add_parser(
            'container',
            help='stop containers.'
        )
        parser_stop_container.add_argument(
            'containers', nargs='+', help='The argument format is the same as \'rm container\'')
        parser_stop_container.set_defaults(func=self.__stop_container)

    '''****************************** some properties of Factory classes ******************************'''

    @property
    def containers(self) -> list[PdtImage]:
        return self.__images

    @property
    def select_list(self) -> PdtImage:
        return self.__selected_image

    @property
    def image_names(self) -> list[str]:
        return [x.name for x in self.__images]

    @property
    def image_apts(self) -> list[set[str]]:
        return [x.apt for x in self.__images]

    @property
    def image_deploys(self) -> list[set[str]]:
        return [x.deploy.files for x in self.__images]

    @property
    def image_details(self) -> list[str]:
        return [x.info_dict for x in self.__images]

    @property
    def command_tree(self) -> dict:
        return self.__get_command_tree(self.__command_tree)

    def __get_command_tree(self, root) -> dict:
        ret = {}
        for k in root:
            if type(root[k]) == dict:
                ret[k] = self.__get_command_tree(root[k])
            else:
                ret[k] = None
        return ret

    '''****************************** functions for all commands ******************************'''

    def __new(self, pc: dict) -> None:
        new_images = pc['name']
        for i in translate_containers(new_images):
            if f"{i}:latest" in self.docker_images_namelist():
                PrettyPrinter.error(f'\'{i}\' exists.')
                continue
            else:
                self.add_image(i)
                PrettyPrinter.info(f'\'{i}\' created.')

    def __select(self, pc: dict) -> None:
        if pc['name'] not in [i.name for i in self.__images]:
            PrettyPrinter.error('image specified do not exist.')
            return
        self.__selected_image = next((i for i in self.__images if i.name == pc['name']), None)

    def __set_parent(self, pc: dict) -> None:
        image_names = self.docker_images_namelist()
        if pc['tag'] not in image_names:
            PrettyPrinter.error(f'image {pc["tag"]} not found in local machine.')
            return
        self.__selected_image.parent = pc['tag']

    def __set_apt(self, pc: dict) -> None:
        if pc['a'] is not None:
            self.__selected_image.apt |= set(pc['a'])
        if pc['r'] is not None:
            self.__selected_image.apt -= set(pc['r'])

    def __set_basedir(self, pc: dict) -> None:
        self.__selected_image.deploy.basedir = pc['base']

    def __set_deploy(self, pc: dict) -> None:
        # ATTENTION: all files cannot have any spaces in its path!!!
        if pc['a'] is not None:
            self.__selected_image.deploy.files |= set(pc['a'])
        if pc['r'] is not None:
            self.__selected_image.deploy.files -= set(pc['r'])

    def __set_entry(self, pc: dict) -> None:
        self.__selected_image.deploy.entry = pc['entry']

    def __set_port(self, pc: dict) -> None:
        self.__selected_image.port = pc['port']

    def __list_image(self, pc: dict) -> None:
        if pc['a']:
            for image in self.__images:
                if pc['d']:
                    print(PrettyPrinter.print_dict_as_a_tree(image.info_dict))
                else:
                    print(image.name)
        else:
            for image in pc['image']:
                if pc['d']:
                    print(PrettyPrinter.print_dict_as_a_tree(image.info_dict))
                else:
                    print(image.__name)

    def __list_apt(self, _: dict) -> None:

        max_name_len = max([len(i.name) for i in self.__images])
        bound = 78 - max_name_len
        data = []
        for image in self.__images:
            data.append([image.name, PrettyPrinter.alignment_of_lists(list(image.apt), bound)])
        chart: pd.DataFrame = pd.DataFrame(data, columns=['name', 'apt list'])
        print(chart)

    def __list_deploy(self, _: dict) -> None:
        max_name_len = max([len(i.name) for i in self.__images])
        bound = 78 - max_name_len
        data = []
        for image in self.__images:
            data.append([image.name, PrettyPrinter.alignment_of_lists(list(image.deploy.files), bound)])
        chart: pd.DataFrame = pd.DataFrame(data, columns=['name', 'deploy'])
        print(chart)

    def __list_select(self, pc: dict):
        if pc['d']:
            print(PrettyPrinter.print_dict_as_a_tree(self.__selected_image.info_dict))
        else:
            print(self.__selected_image.name)

    def __list_status(self, _: dict) -> None:
        data = {}
        for image in self.__images:
            if image.image_object is None:
                data[image.name] = {'status': Style.BRIGHT + Fore.RED + '⬤  ', 'containers': {}}
            else:
                data[image.name] = {'status': Style.BRIGHT + Fore.GREEN + '⬤  ', 'containers': {}}
            data[image.name]['status'] += ('Not Built' if image.image_object is None else "Built") + Style.RESET_ALL
            for cid, container in image.containers:
                data[image.name]['containers'][cid] = (Fore.RED if container.status == 'exited' else Fore.GREEN) \
                                                      + '⬤  ' + Fore.RESET + container.status
        print(PrettyPrinter.print_dict_as_a_tree(data))

    def __build(self, _: dict) -> None:
        self.__selected_image.build()
        self.peek_docker_images()

    def __run(self, pc: dict) -> None:
        pc['ids'] = delayer_list(pc['ids'])
        create_num = pc['n'] if pc['n'] is not None else 0

        # start running existing __containers
        for ctn_id in pc['ids']:
            if type(ctn_id) == type(tuple):
                for i in range(ctn_id[0], ctn_id[1] + 1):
                    if i >= self.__selected_image.container_cnt:
                        PrettyPrinter.error(f'Container id out of bound: {i} (should be smaller than '
                                            f'{self.__selected_image.container_cnt}).')
                        continue
                    if self.__selected_image.container_stat(i) != 'running':
                        self.__selected_image.start_container(i)
            else:
                if not 1 <= ctn_id <= self.__selected_image.container_cnt:
                    PrettyPrinter.error(f'Container id out of bound: '
                                        f'{ctn_id} for {self.__selected_image.container_cnt}.')
                    continue
                if self.__selected_image.container_stat(ctn_id) != 'running':
                    self.__selected_image.start_container(ctn_id)

        # start creating new __containers
        for i in range(create_num):
            self.__selected_image.add_container(outer_port=pc['p'], flag=pc['f'])

    def __rm_image(self, pc: dict) -> None:
        images = pc['images']
        namelist = [i.name for i in self.__images]
        for i in images:
            if i not in namelist:
                PrettyPrinter.error(f'Image {i} not found.')
                continue
            target = next((t for t in self.__images if t.name == i), None)
            if not use_script:
                if pc['y']:
                    PrettyPrinter.info(f'There are {target.container_cnt} containers based on image {i}, deleted.')
                elif pc['n'] and target.container_cnt != 0:
                    PrettyPrinter.info(f'There are {target.container_cnt} containers based on image {i}, skipped.')
                    continue
                elif target.container_cnt != 0:
                    PrettyPrinter.warning(f'There are {target.container_cnt} containers based on image {i}, '
                                          f'Deleting this image will delete all these containers! Continue? <N/y>')
                    choice = input()
                    if choice == 'Y' or choice == 'y':
                        PrettyPrinter.info('Deleted.')
                    else:
                        PrettyPrinter.info('Skipped.')
                        continue
                else:
                    PrettyPrinter.info(f'No container found based on this image, ready to delete.')
            else:
                if not pc['y'] and target.container_cnt != 0:
                    PrettyPrinter.info(f'Skipped {i}')
                    continue
                PrettyPrinter.info(f'Ready to delete image {i}, which has {target.container_cnt} containers.')
            # delete all the containers
            if target.container_cnt != 0:
                target.delete_all_containers()
            target.delete_image()
            # delete this image
            self.__images.remove(target)
            del target

    def __rm_container(self, pc: dict) -> None:
        targets: list[str] = pc['containers']
        ic_range_list = parse_ic_range_list(targets)
        for i, r in ic_range_list.items():
            if i not in self.image_names:
                PrettyPrinter.error(f'specified image {i} not found.')
                continue
            image = next((x for x in self.__images if x.name == i), None)
            # start deleting containers
            image.delete_containers(r)

    def __stop_container(self, pc: dict) -> None:
        targets: list[str] = pc['containers']
        ic_range_list = parse_ic_range_list(targets)
        for i, r in ic_range_list.items():
            if i not in self.image_names:
                PrettyPrinter.error(f'specified image {i} not found.')
                continue
            image = next((x for x in self.__images if x.name == i), None)
            image.stop_containers(r)

    '''****************************** auxiliary methods for executing commands ******************************'''

    def check_set(self, parsed_command: dict):
        """
        Check whether the set command is valid.
        :param parsed_command: command list
        :return: True/False
        """
        if len(parsed_command['commands']) < 3 and parsed_command['commands'][1] in ['entry', 'basedir', 'image',
                                                                                     'port']:
            PrettyPrinter.error(f'no target object selected.')
            return False
        if self.__selected_image.name == 'none':
            PrettyPrinter.info(f'No image selected, this command will do nothing.')
            return False
        return True

    def add_image(self, newone) -> None:
        self.__images.append(PdtImage(newone, self.__docker_client))

    def peek_docker_images(self) -> None:
        self.__docker_images = self.__docker_client.images.list()

    def peek_docker_containers(self) -> None:
        self.__docker_containers = self.__docker_client.__containers.list()

    def docker_images_namelist(self) -> list[str]:
        self.peek_docker_images()
        return delayer_list([n.tags for n in self.__docker_images])

    def arg_parser(self, command):
        # try:
        parsed = self.__arg_parser.parse_args(command)
        parsed.func(parsed.__dict__)
        # except (SystemExit, Exception):
        #     print("Error")


factory = None
use_script = False


def crash_handler():
    pass


def check_dirs():
    if not os.path.exists('./runtime'):
        os.mkdir('./runtime')
    if not os.path.exists('./runtime/deploy_files'):
        os.mkdir('./runtime/deploy_files')
    if not os.path.exists('./runtime/deploy_files/zips'):
        os.mkdir('./runtime/deploy_files/zips')
    if not os.path.exists('./runtime/config.yaml'):
        os.system('touch ./runtime/config.yaml')


signal.signal(signal.SIGINT, crash_handler)
signal.signal(signal.SIGHUP, crash_handler)
signal.signal(signal.SIGTERM, crash_handler)

if __name__ == '__main__':
    check_dirs()
    factory = PdtFactory(load_config())
    if len(sys.argv) > 1 and sys.argv[1] == 'script':
        use_script = True
        if len(sys.argv) < 3:
            PrettyPrinter.error('No scripts specified.')
            exit(0)
        if not os.path.exists(sys.argv[2]):
            PrettyPrinter.error('Script file not found.')
            exit(0)
        with open(sys.argv[2], 'r') as f:
            script_content = f.read()
        script_commands = script_content.split('\n')
        for c in script_commands:
            c = c.strip()
            if len(c) == 0 or c.startswith('#'):    # empty lines and comment lines
                continue
            PrettyPrinter.script(c)
            factory.arg_parser(re.split(r'\s+', c))
            save_config(factory.containers)
        exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == 'command':
        factory.arg_parser(sys.argv[2:])
        save_config(factory.containers)
        exit(0)
    while True:
        cmd = input('pdt> ')
        args = re.split(r'\s+', cmd)
        if len(args) == 0:
            continue
        if args[0] == 'exit':
            print('Bye')
            exit(0)
        factory.arg_parser(args)
        save_config(factory.containers)
