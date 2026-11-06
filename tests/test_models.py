"""Discovery inventory keeps attached cameras on their opener devices."""

from custom_components.myq.models import GarageDoor, MyQCamera, MyQDevices


def test_inventory_excludes_cameras_attached_to_any_discovered_door() -> None:
    attached = MyQCamera("TC-0005-10000001")
    first = MyQCamera("TC-0007-20000001", name="Front entrance")
    second = MyQCamera("TC-0007-20000002", name="Side entrance")
    door = GarageDoor("account-1", "door-1", "Garage", None, "closed", True, camera=attached)
    devices = MyQDevices((door,), (first, attached, second))

    assert devices.standalone_cameras == (first, second)
    assert devices.cameras == (first, attached, second)


def test_inventory_retains_cameras_without_any_garage_doors() -> None:
    camera = MyQCamera("TC-0007-20000001")

    assert MyQDevices(cameras=(camera,)).standalone_cameras == (camera,)
