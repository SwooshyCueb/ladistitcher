import threading
from contextlib import contextmanager
from pprint import pprint
import inspect

class err(Exception):
    pass

class timeout(err):
    pass

class signal_cond(threading.Condition):

    def wait_for(self, predicate, timeout=10):
        if super().wait_for(predicate, timeout) == False:
            result = bool(predicate())
            print('signal_cond timed out :c', flush=True)
            print(inspect.getsource(predicate))
        else:
            return True

    def wait(self, timeout=10):
        return super().wait(timeout)

    def signal(self, n=None):
        if n == None:
            self.notify_all()
        else:
            self.notify(n=n)

    @contextmanager
    def exit_when(self, predicate, timeout=10):
        self.__enter__()
        yield self
        result = self.wait_for(predicate, timeout)
        self.__exit__()
        if result == False:
            raise timeout

    @contextmanager
    def exit_on_signal(self, timeout=10):
        self.__enter__()
        yield self
        result = self.wait(timeout)
        self.__exit__()
        if result == False:
            raise timeout


class signal_lock(threading.Semaphore):

    def __init__(self, buffer_signals=True):
        super().__init__(value=0)
        self.buffer_signals = buffer_signals

    def wait(self, timeout=10):
        return self.acquire(timeout=timeout)

    def signal(self):
        self.release()
        if self.buffer_signals == False:
            self._value = 0

    def reset(self):
        self._value = 0

    def __enter__(self):
        self.reset()
        return self

    def __exit__(self, type, value, traceback):
        if value != None:
            raise value
        if self.wait() == False:
            raise timeout
