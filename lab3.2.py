import threading
import time
import random

class Pot:
    def __init__(self, capacity, num_savages=0):
        self.capacity = capacity
        self.num_savages = num_savages
        self.portions = 0
        self.next_savage = 0
        self.lock = threading.Lock()
        self.output_lock = threading.Lock()  # Блокировка для вывода
        self.empty = threading.Condition(self.lock)
        self.full = threading.Condition(self.lock)

    def print_sync(self, message):
        """Синхронизированный вывод"""
        with self.output_lock:
            print(message)

    def take_portion(self, savage_id):
        with self.lock:
            while self.portions == 0:
                self.print_sync(f"Дикарь {savage_id} ждет, кастрюля пуста")
                self.empty.notify()
                self.full.wait()
            self.portions -= 1
            self.print_sync(f"Дикарь {savage_id} взял порцию. Осталось: {self.portions}")
            return True

    def take_portion_fair(self, savage_id):
        with self.lock:
            while savage_id != self.next_savage:
                self.full.wait()
            
            while self.portions == 0:
                self.print_sync(f"Дикарь {savage_id} будит повара")
                self.empty.notify()
                self.full.wait()
            
            self.portions -= 1
            self.print_sync(f"Дикарь {savage_id} взял порцию. Осталось: {self.portions}")
            
            self.next_savage = (self.next_savage + 1) % self.num_savages
            self.full.notify_all()
            return True

    def fill_pot(self):
        with self.lock:
            while self.portions > 0:
                self.print_sync("Повар ждет, кастрюля еще не пуста")
                self.empty.wait()
            self.portions = self.capacity
            self.print_sync(f"Повар наполнил кастрюлю. Порций: {self.portions}")
            self.full.notify_all()

def savage(savage_id, pot):
    time.sleep(random.uniform(0.1, 0.5))
    pot.take_portion(savage_id)
    pot.print_sync(f"Дикарь {savage_id} поел")

def hungry_savage(savage_id, pot, meals_to_eat=3):
    for meal in range(meals_to_eat):
        time.sleep(random.uniform(0.1, 0.3))
        pot.take_portion_fair(savage_id)
        pot.print_sync(f"Дикарь {savage_id} съел порцию {meal + 1}")
        time.sleep(random.uniform(0.1, 0.2))

def cook(pot, num_savages):
    for _ in range(num_savages // pot.capacity + 1):
        pot.fill_pot()

def continuous_cook(pot):
    while True:
        pot.fill_pot()
        time.sleep(0.1)

def lab3_savages1():
    """Версия 2.1 - каждый дикарь ест один раз"""
    print("=== Lab3Savages1 ===")
    N = 5
    M = 8
    
    pot = Pot(N)
    
    savage_threads = []
    for i in range(M):
        thread = threading.Thread(target=savage, args=(i, pot))
        savage_threads.append(thread)
        thread.start()
    
    cook_thread = threading.Thread(target=cook, args=(pot, M))
    cook_thread.start()
    
    for thread in savage_threads:
        thread.join()
    cook_thread.join()
    
    print("Все дикари поели!\n")

def lab3_savages2():
    """Версия 2.2 - дикари едят многократно с очередью"""
    print("=== Lab3Savages2 ===")
    N = 5
    M = 8
    
    pot = Pot(N, M)
    
    cook_thread = threading.Thread(target=continuous_cook, args=(pot,))
    cook_thread.daemon = True
    cook_thread.start()
    
    savage_threads = []
    for i in range(M):
        thread = threading.Thread(target=hungry_savage, args=(i, pot, 2))
        savage_threads.append(thread)
        thread.start()
    
    for thread in savage_threads:
        thread.join()
    
    print("Все дикари наелись!\n")

def main():
    print("Задача 'Обед дикарей' (Producer-Consumer)\n")
    
    lab3_savages1()
    time.sleep(1)
    lab3_savages2()

if __name__ == "__main__":
    main()