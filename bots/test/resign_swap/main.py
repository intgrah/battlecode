from cambc import Controller


class Player:
    def run(self, ct: Controller) -> None:
        Controller.get_entity_type = Controller.resign
