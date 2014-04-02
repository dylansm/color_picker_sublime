import os
import re
import subprocess
import sublime
import sublime_plugin
from pprint import pprint


class CodeColorPickerCommand(sublime_plugin.TextCommand):

    def run(self, edit, **args):
        self.edit = edit
        # match rgb(255, 255, 255) and rgba(24, 24, 24, 0.5) and #555 and
        # #555555
        #self.COLOR_DECLARATION_REGEXP = re.compile(
            #'rgb\(\s?(\d+,\s?){2}\d+\s?\)|' +
            #'rgba\(\s?(\d+,\s?){3}\d{1}?\.?\d+?\s?\)|' +
            #'#[0-9a-f]+', re.I)
        self.COLOR_DECLARATION_REGEXP = re.compile(
            'rgb\(\s?(\d+,\s?){2}\d+\s?\)|' +
            'rgba\(\s?(\d+,\s?){3}\d?(\.[0-9]{1,2})?\s?\)|' +
            '#[0-9a-f]+', re.I)
        self.COLOR_REGEXP = re.compile(
            '(?<=rgb\()\s?(\d+,\s?){2}\d+\s?(?!=\))|' +
            '(?<=rgba\()\s?(\d+,\s?){3}\d?(\.[0-9]{1,2})?\s?(?!=\))|' +
            '(?<=\#)[0-9a-f]{3,6}(?!=(\D|\W|\n|;))+', re.I)
        self.RGB_MAX = 65535

        self.get_selection()

        if args["cmd"] == 'picker':
            try:
                self.values = self.parse_selection()
                self.convert_8bit_to_16bit()
                self.trigger_chooser()
                self.insert_sampled_color_text()
            except AttributeError:
                sublime.status_message('No color codes found in selection.')
        elif args["cmd"] == 'cycler':
            try:
                self.values = self.parse_selection()
                print(self.values)
                #self.convert_8bit_to_16bit()
                #self.trigger_chooser()
                #self.insert_sampled_color_text()
            except AttributeError:
                sublime.status_message('No color codes found in selection.')

    def get_selection(self):
        selections = self.view.sel()
        for region in selections:
            if region.empty():
                self.is_line = True
                line = self.view.line(region)
                self.region = line
                self.original_selection = self.view.substr(line)
            else:
                # detect whether this was a hex selection without '#'
                prev_char = self.view.substr(
                    sublime.Region(region.a - 1, region.a))
                if prev_char == "#":
                    self.region = sublime.Region(region.a - 1, region.b)
                    self.original_selection = self.view.substr(self.region)
                else:
                    self.region = region
                    self.original_selection = self.view.substr(region)

        s = self.original_selection
        colors = self.COLOR_REGEXP.search(s)
        if colors is not None:
            self.selection = colors.group()
        string_values = self.COLOR_DECLARATION_REGEXP.search(s)
        if string_values is not None:
            self.string_values = string_values.group(0)

    def parse_selection(self):
        # reduce 4 and 5 digit hex values to 3
        val_length = len(self.selection)
        if (3 < val_length < 6):
            values = self.selection[0:3]
        else:
            values = self.selection

        if "," not in values:
            return self.convert_hex_str_to_8bit(values)
        else:
            return self.convert_rgb_str_to_8bit(values)

    def trigger_chooser(self):
        subprocess.Popen(['osascript', '-e', 'tell app "Finder" to activate'])
        cmd = '''
    tell app "Finder" to activate
    tell app "Finder" to choose color default color {{{0}, {1}, {2}}}
    '''
        self.sampled_colors = subprocess.Popen(
            ['osascript', '-e',
                cmd.format(
                    self.values["r"], self.values["g"], self.values["b"])],
            stdout=subprocess.PIPE).communicate()[0].decode(encoding='UTF-8').rstrip('\n')
        subprocess.Popen(
            ['osascript', '-e', 'tell app "System Events" to keystroke "h" using command down'])

    def convert_hex_str_to_8bit(self, values):
        rgb = []
        if len(values) == 3:
            for char in values:
                rgb.append((int(char, 16) << 4 | int(char, 16)) + 1)
        else:
            rgb.append(int(values[0:2], 16) + 1)
            rgb.append(int(values[2:4], 16) + 1)
            rgb.append(int(values[4:6], 16) + 1)

        return self.rgba_dict(rgb)

    def convert_rgb_str_to_8bit(self, values):
        rgba = []
        for i, v in enumerate(values.split(",")):
            if i < 3:
                rgba.append(int(v, 10))
            else:
                rgba.append(float(v))
        return self.rgba_dict(rgba)

    def convert_8bit_to_16bit(self):
        for key in self.values:
            if key != "a":
                _16bit = (self.values[key] << 8) + 1
                if _16bit > self.RGB_MAX:
                    _16bit = self.RGB_MAX
                self.values[key] = _16bit

    def rgba_dict(self, rgb):
        if (len(rgb) == 3):
            return dict(zip(["r", "g", "b"], rgb))
        else:
            return dict(zip(["r", "g", "b", "a"], rgb))

    def insert_sampled_color_text(self):
        new_colors = self.map_sampled_color_format()
        if self.is_line:
            # replace original selection's colors with new_colors
            # then put that longer string back in line
            new_string = self.original_selection.replace(
                self.string_values, new_colors)
            self.view.replace(self.edit, self.region, new_string)
        else:
            self.view.replace(self.edit, self.region, new_colors)

    def map_sampled_color_format(self):
        if "#" in self.string_values:
            return self.convert_16bit_to_hex()
        else:
            return self.convert_16bit_to_rgb()

    def convert_16bit_to_hex(self):
        values = self.sampled_colors.split(",")
        hex_str = ""
        for v in values:
            hex_str += "{:02x}".format((int(v, 10) >> 8))
            hex_str = self.reduce_hex(hex_str)
        return "#%s" % hex_str

    def reduce_hex(self, hex_str):
        new_hex_str = ""
        for i, v in enumerate(hex_str):
            if i % 2 == 0 and hex_str[i + 1] == v:
                new_hex_str += v
        return new_hex_str if len(new_hex_str) == 3 else hex_str

    def convert_16bit_to_rgb(self):
        values = self.sampled_colors.split(",")
        for i, v in enumerate(values):
            values[i] = int(v, 10) >> 8
        if 'a' in self.values:
            print(values[0])
            print(values[1])
            print(values[2])
            print("%1.1f" % self.values["a"])
            return "rgba(%d, %d, %d, %1.1f)" % (values[0], values[1], values[2], self.values["a"])
        else:
            return "rgb(%d, %d, %d)" % (values[0], values[1], values[2])
        return values
