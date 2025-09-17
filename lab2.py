from typing import List

class Car:
    def __init__(self, brand: str, model: str, fuel_consumption: float, price: float, max_speed: float):
        self.brand = brand
        self.model = model
        self.fuel_consumption = fuel_consumption #расход топлива
        self.price = price 
        self.max_speed = max_speed  
    
    def __str__(self):
        return f"{self.brand} {self.model} - {self.fuel_consumption} л/100км, {self.price} руб., {self.max_speed} км/ч"

class CarPark:
    def __init__(self):
        self.cars: List[Car] = []
    
    def add_car(self, car: Car) -> None:
        self.cars.append(car)
    
    def get_total_cost(self) -> float:
        total = 0.0
        for car in self.cars:
            total += car.price
        return total
    
    def sort_by_fuel_consumption(self) -> List[Car]:
        return sorted(self.cars, key=lambda x: x.fuel_consumption)
    
    def find_cars_by_speed_range(self, min_speed: float, max_speed: float) -> List[Car]:
        result = []
        for car in self.cars:
            if min_speed <= car.max_speed <= max_speed:
                result.append(car)
        return result


if __name__ == "__main__":
    taxi_park = CarPark()
    
    taxi_park.add_car(Car("Toyota", "Camry", 8.5, 2500000, 210))
    taxi_park.add_car(Car("Lada", "Vesta", 7.8, 1200000, 180))
    taxi_park.add_car(Car("BMW", "X5", 9.2, 5500000, 230))
    taxi_park.add_car(Car("Kia", "Rio", 6.9, 1500000, 190))
    taxi_park.add_car(Car("Mercedes", "E-Class", 8.1, 4800000, 240))
    
    # 1. Подсчитать стоимость автопарка
    total_cost = taxi_park.get_total_cost()
    print(f"Общая стоимость автопарка: {total_cost:,.2f} руб.")
    print()
    
    # 2. Сортировка по расходу топлива
    sorted_cars = taxi_park.sort_by_fuel_consumption()
    print("Автомобили, отсортированные по расходу топлива (по возрастанию):")
    for i, car in enumerate(sorted_cars, 1):
        print(f"{i}. {car}")
    print()
    
    # 3. Поиск по диапазону скоростей
    min_speed = 200
    max_speed = 230
    speed_cars = taxi_park.find_cars_by_speed_range(min_speed, max_speed)
    print(f"Автомобили со скоростью от {min_speed} до {max_speed} км/ч:")
    for car in speed_cars:
        print(f"- {car.brand} {car.model}: {car.max_speed} км/ч")

