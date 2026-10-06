from playwright.sync_api import expect


def close_panel(page):
    """Return through the visible panel control before interacting with the board."""
    dialog = page.locator('dialog[open]')
    if dialog.count():
        button = dialog.get_by_role('button', name='返回看板', exact=True)
        if not button.count():
            button = dialog.get_by_role('button', name='Back to board', exact=True)
        expect(button).to_be_enabled()
        button.click()
        expect(dialog).to_have_count(0)
