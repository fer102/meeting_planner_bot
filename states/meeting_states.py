from aiogram.fsm.state import State, StatesGroup

class CreateMeeting(StatesGroup):
    title = State()
    description = State()
    choosing_dates = State()
    choosing_time = State()
    confirm = State()

class Voting(StatesGroup):
    viewing_options = State()
    voting = State()
    results = State()

class BroadcastMessage(StatesGroup):
    choosing_meeting = State()
    typing_message = State()
    confirm = State()

class EditMeeting(StatesGroup):
    choosing_option = State()
    adding_new_time = State()
    confirm = State()