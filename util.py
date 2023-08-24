import os
import re
import yaml
import uuid
from typing import Union
from colorama import Fore, Back, Style
import pandas as pd

PDT_CONSOLE = 'pdt> '
PDT_ERROR = 'pdt: [x] '
PDT_WARN = 'pdt: [!]'
PDT_INFO = 'pdt: [o] '
PDT_SCRIPT = '+ '
FLAG_HEADER = 'flag'

RUNTIME_DIR = './runtime'
DEPLOY_FILE_DIR = './runtime/deploy_files'
ZIP_DIR = './runtime/deploy_files/zips'
USER = 'ctf'
BASEDIR_IN_DOCKER = '/home/' + USER


class PrettyPrinter:
    @staticmethod
    def error(message, fore=Fore.RED, back=Back.RESET, style=Style.BRIGHT):
        print(Fore.RED + PDT_ERROR, end='')
        print(fore + back + style + message + Style.RESET_ALL)

    @staticmethod
    def info(message, fore=Fore.BLUE, back=Back.RESET, style=Style.BRIGHT):
        print(Fore.BLUE + PDT_INFO, end='')
        print(fore + back + style + message + Style.RESET_ALL)

    @staticmethod
    def warning(message, fore=Fore.YELLOW, back=Back.RESET, style=Style.BRIGHT):
        print(Fore.YELLOW + PDT_WARN, end='')
        print(fore + back + style + message + Style.RESET_ALL)

    @staticmethod
    def script(message, fore=Fore.YELLOW, back=Back.RESET, style=Style.BRIGHT):
        print(Fore.YELLOW + PDT_SCRIPT, end='')
        print(fore + back + style + message + Style.RESET_ALL)

    @staticmethod
    def print_dict_as_a_tree(i, indent=0, color_sign=None) -> str:
        """
        input a dict like a tree, for example: {'a': 'aa', 'b': ['c', {'d': 'dd}]} will be printed out as:

        a: aa
        b:
            c
            d: dd

        :param indent: indentation length
        :param i: input dict
        :return: None
        """
        if color_sign is None:
            color_sign = {}
        ret = ''
        if isinstance(i, list):
            if not i:
                ret += '    ' * indent + '[empty]\n'
                return ret
            for e in i:
                if not isinstance(e, Union[list, dict]):
                    ret += '    ' * indent + str(e) + '\n'
                else:
                    indent += 1
                    ret += PrettyPrinter.print_dict_as_a_tree(e, indent, color_sign=color_sign)
                    indent -= 1
        elif isinstance(i, dict):
            if i == {}:
                ret += '    ' * indent + '{empty}\n'
                return ret
            for k in i.keys():
                if color_sign is not None and k in color_sign.keys():
                    ret += color_sign[k]
                ret += '    ' * indent + str(k) + ": "
                if not isinstance(i[k], Union[list, dict]):
                    ret += str(i[k]) + '\n'
                else:
                    ret += '\n'
                    indent += 1
                    ret += PrettyPrinter.print_dict_as_a_tree(i[k], indent, color_sign=color_sign)
                    indent -= 1
                ret += Fore.RESET
        else:
            ret += '    ' * indent + str(i) + '\n'
        return ret

    @staticmethod
    def alignment_of_lists(l: list, bound: int):
        """
        get the string of a list, but may be divided into lines, the length of every line is bounded to a value.
        :param bound: the maximum length of every line
        :param l: input list
        :return: pretty version
        """
        lines = []
        newline = ''
        for e in l:
            if newline != '':
                newline += ' '
            if len(str(e)) > bound:
                ptr = bound - len(newline) - 1
                newline += str(e)[:bound-len(newline)-1] + '↙'
                lines.append(newline)
                while len(e) - ptr > bound:
                    newline = str(e[ptr:ptr+bound-1]) + '↙'
                    lines.append(newline)
                    ptr += bound - 1
                else:
                    newline = str(e[ptr:]) + ' '
                    continue
            elif len(str(e)) + len(newline) <= bound - 1:
                newline += str(e)
            else:
                lines.append(newline)
                newline = str(e)
        lines.append(newline)
        return '\n'.join(lines)

def delayer_list(l: list) -> list:
    """
    Used for eliminating recursion of a list, for example, turning [['a', 'b'], 'c'] into ['a', 'b', 'c']
    :param l: input list
    :return: output list
    """
    ret = []
    for e in l:
        if str(type(e)) == '<class \'list\'>':
            ret += delayer_list(e)
        else:
            ret.append(e)
    return ret


def translate_containers(l: list):
    """
    Used for translating given list into container list.
    In PDT, we allow user to input '*' to define multiple containers, this function will translate
    it into individuals, like 'pwn*2' will be translated into 'pwn_0' and 'pwn_1'
    :param l: input list, it can come from user command 'select' and 'new'
    :return: valid container list
    """
    result = []
    for e in l:
        if e.count('*') > 1 or re.search(r'[^a-zA-Z0-9_*]', e):
            PrettyPrinter.error('unexpected character in container name, only letters, digits and underlines allowed.')
            continue
        if e.count('*') == 1:
            container_name, count = e.split('*')
            try:
                count = int(count)
            except Exception:
                PrettyPrinter.error('cannot parse the count, string after * must be a number.')
                continue
        else:
            count = 1
            container_name = e
        if count == 1:
            result.append(container_name)
        else:
            for c in range(count):
                newone = container_name + '_' + str(c)
                result.append(newone)
    return result


def analyse_console_table(output: str) -> pd.DataFrame:
    lines = output.split('\n')
    header = re.split(r'\s{2,}', lines[0])
    data = [re.split(r'\s{2,}', line) for line in lines[1:-1]]
    df = pd.DataFrame(data, columns=header)
    return df


def save_config(images: list):
    file = open('./runtime/config.yaml', 'w', encoding='UTF-8')
    config_data = []
    for c in images:
        config_data.append(c.info_dict_for_config)
    yaml.dump(config_data, file)
    file.close()


def load_config():
    with open('./runtime/config.yaml', 'r') as f:
        data = yaml.safe_load(f.read())
    return data


def flag_generator(number: int) -> list:
    ret = []
    for i in range(number):
        ret.append(FLAG_HEADER + '{' + str(uuid.uuid4()) + '}')
    return ret


def file_in_list(files, target):
    for f in files:
        pass


def relative_to_absolute_path(rel):
    current_dir = os.getcwd()
    absolute_path = os.path.abspath(os.path.join(current_dir, rel))
    if os.path.exists(absolute_path):
        return absolute_path
    else:
        return None
