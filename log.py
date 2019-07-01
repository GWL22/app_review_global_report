import datetime as dt


class Log:
    def __init__(self, log_file):
        self.logf = log_file

    def write(self, line):
        now_time = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.logf, 'a+') as f:
            f.write(f'[{now_time}] {line}\n')

    def write_info(self, line):
        line = f'[INFO] {line}'
        self.write(line)

    def write_warn(self, line):
        line = f'[WARNING] {line}'
        self.write(line)

    def write_err(self, line):
        line = f'[ERROR] {line}'
        self.write(line)

    def write_suc(self, line):
        line = f'[SUCCESS] {line}'
        self.write(line)
