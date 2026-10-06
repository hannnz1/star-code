"""Textual frontend backed exclusively by the durable HTTP task service."""
import asyncio
from typing import ClassVar

import httpx
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, RichLog, Static

from muse.terminal import HELP, complete_command, connect_terminal


class MuseApp(App):
    TITLE = 'Crew'
    SUB_TITLE = 'Your AI commerce team.'
    BINDINGS: ClassVar = [('ctrl+q', 'quit', '退出界面（任务继续）')]
    CSS = '''
    Screen { background: $surface; }
    #task-state { height: 3; padding: 1 2; background: $panel; }
    RichLog { height: 1fr; padding: 1 2; }
    Input { margin: 1 2; }
    '''

    def __init__(self, terminal):
        super().__init__()
        self.terminal = terminal
        self.command_lock = asyncio.Lock()
        self.last_result = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static('等待任务', id='task-state')
        yield RichLog(wrap=True, markup=False, id='output')
        yield Input(placeholder='输入目标，或 /help 查看命令', id='prompt')
        yield Footer()

    def on_mount(self):
        self.query_one(RichLog).write(HELP)
        self.query_one(Input).focus()
        self.set_interval(2, self.refresh_status)

    async def on_input_submitted(self, event: Input.Submitted):
        line = event.value.strip()
        if not line:
            return
        event.input.value = ''
        event.input.disabled = True
        try:
            await self.handle_line(line)
        finally:
            event.input.disabled = False
            event.input.focus()

    def on_key(self, event):
        if event.key != 'tab':
            return
        prompt = self.query_one(Input)
        matches = complete_command(prompt.value)
        if matches:
            event.prevent_default()
            event.stop()
            if len(matches) == 1:
                prompt.value = matches[0] + ' '
                prompt.cursor_position = len(prompt.value)
            else:
                self.query_one(RichLog).write('  '.join(matches))

    async def handle_line(self, line):
        async with self.command_lock:
            log = self.query_one(RichLog)
            if line.strip() == '/watch':
                log.write('顶部自动刷新当前任务状态；/events 查看执行记录。')
                return
            log.write('> ' + line)
            try:
                log.write(await asyncio.to_thread(self.terminal.handle, line))
            except EOFError:
                self.exit()
            except (ValueError, httpx.HTTPError) as error:
                log.write(str(error))
        await self.refresh_status()

    async def refresh_status(self):
        if self.command_lock.locked():
            return
        async with self.command_lock:
            state = self.query_one('#task-state', Static)
            if self.terminal.task_id is None:
                state.update('等待任务 · 输入目标以创建后台任务')
                return
            try:
                task = await asyncio.to_thread(self.terminal.task)
                state.update(f"{task['id'][:12]} · {task['status']} · {task.get('permission_mode', 'default')} · {task['prompt'][:80]}")
                outcome = (task['id'], task.get('result'), task.get('error'))
                if outcome != self.last_result and (outcome[1] or outcome[2]):
                    self.query_one(RichLog).write(outcome[1] or outcome[2])
                    self.last_result = outcome
            except (ValueError, httpx.HTTPError) as error:
                state.update('连接未完成：' + str(error))


def run_tui(settings, workspace, *, permission_mode='default'):
    with connect_terminal(settings, workspace) as terminal:
        terminal.permission_mode = permission_mode
        MuseApp(terminal).run()
