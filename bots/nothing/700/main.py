from cambc import Controller


class Player:
    def run(self, ct: Controller) -> None:
        if ct.get_current_round() == 700:
            ct.resign()
