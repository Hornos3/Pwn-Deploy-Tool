import sys
import signal
import os.path
import argparse
from help import *
from pdt_object import *
from typing import Callable


class PdtFactory:
    def __init__(self, images):
        self.__docker_images: pd.DataFrame = pd.DataFrame()
        self.__docker_containers: pd.DataFrame = pd.DataFrame()
        self.__images: list[PdtImage] = []
        if images is not None:
            for i in images:
                new_container = PdtImage(i['name'])
                new_container.initialize(i)
                self.__images.append(new_container)
        self.__selected_image: PdtImage = PdtImage('none')
        self.update_image_list()
        self.__command_tree = {
            'new': self.__new,
            'select': self.__select,
            'set': {
                'image': self.__set_image,
                'apt': self.__set_apt,
                'basedir': self.__set_basedir,
                'deploy': self.__set_deploy,
                'undeploy': self.__set_undeploy,
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

    '''****************************** some properties of Factory classes ******************************'''

    @property
    def containers(self) -> list[PdtImage]:
        return self.__images

    @property
    def select_list(self) -> PdtImage:
        return self.__selected_image

    @property
    def container_names(self) -> list[str]:
        return [x.name for x in self.__images]

    @property
    def container_apts(self) -> list[set[str]]:
        return [x.apt for x in self.__images]

    @property
    def container_deploys(self) -> list[set[str]]:
        return [x.deploy.files for x in self.__images]

    @property
    def container_details(self) -> list[str]:
        return [x.info_dict for x in self.__images]

    '''****************************** functions for all commands ******************************'''

    def __exec_commands(self, parsed_commands, layer: dict[str, dict] | dict[str, Callable] = None, depth=0) -> None:
        """
        This function is used to interact with command lists, it's recursive.
        :param parsed_commands: unresolved commands
        :param layer: current layer of command tree, always a dict.
                      if a command has subcommands, its value should be a dict,
                      or else, its value should be a function for executing this command.
        :param depth: the depth of current command tree node, which means that how many
                      commands were searched.
        :return: None
        """
        if layer is None:
            layer = self.__command_tree
        if len(parsed_commands['commands']) <= depth:
            if len(parsed_commands['commands']) == 0:
                return
            else:
                PrettyPrinter.error(f'Subcommand needed after command {parsed_commands["commands"][depth - 1]}.')
                return
        if parsed_commands['commands'][depth] not in layer:
            PrettyPrinter.error(f'command not found: {parsed_commands["commands"][depth]}')
            return
        if isinstance(layer[parsed_commands['commands'][depth]], Callable):
            layer[parsed_commands['commands'][depth]](parsed_commands)
        else:
            self.__exec_commands(parsed_commands, layer[parsed_commands["commands"][depth]], depth + 1)

    def __new(self, parsed_command: dict) -> None:
        new_images = parsed_command['commands'][1:]
        for i in translate_containers(new_images):
            if i in [image.name for image in self.__images]:
                PrettyPrinter.error(f'\'{i}\' exists.')
                continue
            else:
                self.add_container(i)
                PrettyPrinter.info(f'\'{i}\' created.')

    def __select(self, parsed_command: dict) -> None:
        if len(parsed_command['commands']) < 2:
            PrettyPrinter.error('No image selected.')
            return
        if parsed_command['commands'][1] not in [i.name for i in self.__images]:
            PrettyPrinter.error('image specified do not exist.')
            return
        self.__selected_image = [i for i in self.__images if i.name == parsed_command['commands'][1]][0]

    def __set_image(self, parsed_command: dict) -> None:
        image_names = self.docker_images_namelist()
        if len(parsed_command['commands']) < 3:
            PrettyPrinter.error(f'no image selected.')
            return
        if parsed_command['commands'][2] not in image_names:
            PrettyPrinter.error(f'image {parsed_command["commands"][2]} not found in local machine.')
            return
        self.__selected_image.image = parsed_command['commands'][2]

    def __set_apt(self, parsed_command: dict) -> None:
        if not self.check_set(parsed_command):
            return
        if set(parsed_command['add']) is not None:
            self.__selected_image.apt |= set(parsed_command['add'])
        if set(parsed_command['rm']) is not None:
            self.__selected_image.apt -= set(parsed_command['rm'])

    def __set_basedir(self, parsed_command: dict) -> None:
        if not self.check_set(parsed_command):
            return
        self.__selected_image.deploy.basedir = parsed_command['commands'][2]

    def __set_deploy(self, parsed_command: dict) -> None:
        # ATTENTION: all files cannot have any spaces in its path!!!
        if not self.check_set(parsed_command):
            return
        self.__selected_image.deploy.files |= set(parsed_command['commands'][2:])

    def __set_undeploy(self, parsed_command: dict) -> None:
        if not self.check_set(parsed_command):
            return
        self.__selected_image.deploy.files -= set(parsed_command['commands'][2:])

    def __set_entry(self, parsed_command: dict) -> None:
        if not self.check_set(parsed_command):
            return
        self.__selected_image.deploy.entry = parsed_command['commands'][2]

    def __set_port(self, parsed_command: dict) -> None:
        if not self.check_set(parsed_command):
            return
        try:
            port = int(parsed_command['commands'][2])
        except ValueError:
            PrettyPrinter.error('Port input is not a valid integer.')
            return
        self.__selected_image.port = port

    def __list_image(self, parsed_command: dict) -> None:
        for image in self.__images:
            if parsed_command['detail']:
                print(PrettyPrinter.print_dict_as_a_tree(image.info_dict))
            else:
                print(image.name)

    def __list_apt(self, parsed_command: dict) -> None:
        max_name_len = max([len(i.name) for i in self.__images])
        bound = 78 - max_name_len
        data = []
        for image in self.__images:
            data.append([image.name, PrettyPrinter.alignment_of_lists(list(image.apt), bound)])
        chart: pd.DataFrame = pd.DataFrame(data, columns=['name', 'apt list'])
        print(chart)

    def __list_deploy(self, parsed_command: dict) -> None:
        max_name_len = max([len(i.name) for i in self.__images])
        bound = 78 - max_name_len
        data = []
        for image in self.__images:
            data.append([image.name, PrettyPrinter.alignment_of_lists(list(image.deploy.files), bound)])
        chart: pd.DataFrame = pd.DataFrame(data, columns=['name', 'deploy'])
        print(chart)

    def __list_select(self, parsed_command: dict):
        if parsed_command['detail']:
            print(PrettyPrinter.print_dict_as_a_tree(self.__selected_image.info_dict))
        else:
            print(self.__selected_image.name)

    def __list_status(self, parsed_command: dict) -> None:
        data = {}
        for image in self.__images:
            if image.status == 'unallocated':
                data[image.name] = {'status': Style.BRIGHT + Fore.RED + '⬤  ', 'containers': {}}
            else:
                data[image.name] = {'status': Style.BRIGHT + Fore.GREEN + '⬤  ', 'containers': {}}
            data[image.name]['status'] += image.status + Style.RESET_ALL
            for cid, container in image.containers:
                data[image.name]['containers'][cid] = (Fore.RED if container.status == 'exited' else Fore.GREEN) \
                                                      + '⬤  ' + Fore.RESET + container.status
        print(PrettyPrinter.print_dict_as_a_tree(data))

    def __build(self, parsed_command: dict) -> None:
        self.__selected_image.build()
        self.update_image_list()

    def __run(self, parsed_command: dict) -> None:
        if len(parsed_command['commands']) > 1:
            try:
                run_ids = [int(i) for i in parsed_command['commands'][1:]]
            except ValueError:
                PrettyPrinter.error('Specified id is not a number.')
                return
        else:
            run_ids = []
        if parsed_command['new'] is not None:
            try:
                create_num = int(parsed_command['new'])
            except ValueError:
                PrettyPrinter.error('Specified new containers\' count is not a number')
                return
        else:
            create_num = 0
        if parsed_command['op'] is not None:
            try:
                start_port = int(parsed_command['op'])
            except ValueError:
                PrettyPrinter.error('Specified port is not a number')
                return
        else:
            start_port = 0
        run_count = len(run_ids) + create_num
        if parsed_command['flag'] is not None:
            flag = parsed_command['flag'] * run_count
        else:
            flag = flag_generator(run_count)

        # start running existing containers
        for ctn_id in run_ids:
            if ctn_id not in self.__selected_image.containers.keys():
                PrettyPrinter.error(f'no container found for id {ctn_id}.')
                continue
            os.system(f'docker start {self.__selected_image.containers[ctn_id].container_id}')

        # start creating new containers
        for i in range(create_num):
            next_id = self.__selected_image.next_container_id()
            run_command = f'docker run '
            new_container = PdtContainer(self.__selected_image)
            new_container.id = next_id
            new_container.status = 'running'
            new_container.outer_port = start_port + i if start_port != 0 else 0
            if new_container.outer_port != 0:
                run_command += f'-p {new_container.outer_port}:{self.__selected_image.port}'
            run_command += f' -d {self.__selected_image.name}'
            new_container.flag = flag[i]
            docker_run_process = subprocess.run(run_command, stdout=subprocess.PIPE, shell=True)
            container_id = docker_run_process.stdout.strip()[:12].decode()
            new_container.container_id = container_id
            PrettyPrinter.info(f'Successfully created a container, id={next_id}, container_id={container_id}')
            self.__selected_image.containers[next_id] = new_container

    def __rm_image(self, parsed_command: dict) -> None:
        if len(parsed_command['commands']) < 3:
            PrettyPrinter.error('no image specified.')
            return
        images = parsed_command['commands'][2:]
        namelist = [i.name for i in self.__images]
        for i in images:
            if i not in namelist:
                PrettyPrinter.error(f'Image {i} not found.')
                continue
            target = next((t for t in self.__images if t.name == i), None)
            if not use_script:
                if parsed_command['yes']:
                    PrettyPrinter.info(f'There are {len(target.containers)} containers based on image {i}, deleted.')
                elif parsed_command['no'] and len(target.containers.keys()) != 0:
                    PrettyPrinter.info(f'There are {len(target.containers)} containers based on image {i}, skipped.')
                    continue
                elif len(target.containers.keys()) != 0:
                    PrettyPrinter.warning(f'There are {len(target.containers)} containers based on image {i}, '
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
                if not parsed_command['yes'] and len(target.containers.keys()) != 0:
                    PrettyPrinter.info(f'Skipped {i}')
                    continue
                PrettyPrinter.info(f'Ready to delete image {i}, which has {len(target.containers)} containers.')
            # delete all the containers
            if len(target.containers) != 0:
                target.delete_all_container()
            # delete this image
            os.system(f'docker rmi {target.image_id}')
            self.__images.remove(target)
            del target

    def __rm_container(self, parsed_command: dict) -> None:
        if len(parsed_command['commands']) < 3:
            PrettyPrinter.error('no container specified.')
            return
        targets: list[str] = parsed_command['commands'][2:]
        for t in targets:
            if t.count('.') != 1:
                PrettyPrinter.error(f'Command format error: {t}')
                return
            image_name, cids = t.split('.')[0:2]
            image = next((t for t in self.__images if t.name == image_name), None)
            if image is None:
                PrettyPrinter.error(f'specified image {image_name} not found.')
                continue
            cid: list[str] = cids.split(',')
            # analysing delete list
            rm_dict = {}
            for cr in cid:
                match = re.search(r'^(\d+)-(\d+)$', cr)
                if not match:
                    PrettyPrinter.error(f'Format error: {cr}, skipped')
                    continue
                start = int(match.group(1))
                end = int(match.group(2))
                rm_dict[start] = end
            # start deleting containers
            image.delete_containers(rm_dict)

    '''****************************** auxiliary methods for executing commands ******************************'''

    def update_image_list(self):
        self.__docker_images: pd.DataFrame = \
            analyse_console_table(
                subprocess.Popen('docker images', shell=True, stdout=subprocess.PIPE).stdout.read().decode())

    def update_container_list(self):
        self.__docker_containers: pd.DataFrame = \
            analyse_console_table(
                subprocess.Popen('docker ps ' +
                                 ' '.join(['-f ancestor=' + image.name for image in self.__images]) + ' -a',
                                 shell=True, stdout=subprocess.PIPE).stdout.read().decode()
            )

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

    def add_container(self, newone) -> None:
        self.__images.append(PdtImage(newone))

    def peek_docker_images(self) -> None:
        console_out = subprocess.Popen('docker images', shell=True, stdout=subprocess.PIPE).stdout.read().decode()
        self.__docker_images = analyse_console_table(console_out)

    def docker_images_namelist(self) -> list[str]:
        self.peek_docker_images()
        name = self.__docker_images['REPOSITORY']
        version = self.__docker_images['TAG']
        return [f'{n}:{v}' for n, v in zip(name, version)]

    def arg_parser(self, command):
        parser = argparse.ArgumentParser(usage=Help.get_help_str())
        parser.add_argument('commands', nargs='*')
        parser.add_argument('-d', '--detail', action='store_true')
        parser.add_argument('-n', '--new', action='store')
        parser.add_argument('-a', '--all', action='store_true')
        parser.add_argument('-f', '--flag', action='store')
        parser.add_argument('--op', action='store')
        parser.add_argument('-y', '--yes', action='store_true')
        parser.add_argument('--no', action='store_true')
        a = parser.parse_args(command).__dict__
        self.__exec_commands(a)


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
            PrettyPrinter.script(c)
            factory.arg_parser(re.split(r'\s+', c))
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
        main_cmd = args[0]
        if main_cmd == 'help':
            Help.help()
            continue
        if 'help' in args:
            Help.help(main_cmd)
            continue
        factory.arg_parser(args)
        save_config(factory.containers)
