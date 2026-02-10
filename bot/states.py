from aiogram.fsm.state import State, StatesGroup


class RegStates(StatesGroup):
    waiting_contact = State()
    waiting_fio = State()
    waiting_district = State()

class DevNotify(StatesGroup):
    waiting_text = State()

class DriverTaskCreate(StatesGroup):
    waiting_address = State()
    waiting_title = State()
    waiting_safe_code = State()
    waiting_comment = State()

class PenaltyFSM(StatesGroup):
    choosing_user = State()      # выбор сотрудника
    entering_amount = State()    # ввод суммы штрафа
    entering_reason = State()

class TaskCreate(StatesGroup):
    waiting_address = State()
    waiting_title = State()
    waiting_description = State()
    waiting_safe_code = State()
    waiting_comment = State()
    waiting_executor = State()

class BonusStates(StatesGroup):
    waiting_fio = State()
    waiting_amount = State()

class RankAssign(StatesGroup):
    waiting_user = State()
    waiting_rank = State()

class TaskWork(StatesGroup):
    waiting_media = State()
    waiting_missing_text = State()
    waiting_damage = State()
    waiting_remaining_photo = State()


class SearchUser(StatesGroup):
    waiting_query = State()


class RemoveBonus(StatesGroup):
    waiting_user = State()
    waiting_amount = State()
    waiting_reason = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()


class AddressCreate(StatesGroup):
    waiting_title = State()
    waiting_floor = State()
    waiting_apartment = State()
    waiting_description = State()