import json


class Help:
    @staticmethod
    def help(key='all'):
        help_f = open("./help_doc.json", 'r')
        help_content = json.load(help_f)
        if key not in help_content.keys():
            print('pdt: help argument not found, try \'help\' to list all arguments.')
        for line in help_content[key]:
            print(line)

    @staticmethod
    def get_help_str(key='all'):
        help_f = open("./help_doc.json", 'r')
        help_content = json.load(help_f)
        if key not in 'all':
            return None
        return '\n'.join(help_content[key])