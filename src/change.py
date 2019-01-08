"""
Support for displaying the change in value over a specified amount of hours.

"""
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_NAME, STATE_UNKNOWN, ATTR_UNIT_OF_MEASUREMENT)
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.event import async_track_point_in_time


_LOGGER = logging.getLogger(__name__)

ATTR_DELTA = 'delta'
ATTR_ACCU = 'accu'
ATTR_PREV_VALUE = 'prev_value'
ATTR_LAST_UPDATE = 'last_update'

ATTR_TO_PROPERTY = [
    ATTR_DELTA,
    ATTR_ACCU,
    ATTR_LAST_UPDATE,
    ATTR_PREV_VALUE
]

CONF_ENTITY_IDS = 'entity_ids'
CONF_ROUND_DIGITS = 'round_digits'
CONF_TIMESPAN = 'timespan'

ICON = 'mdi:calculator'

DEFAULT_TIMESPAN = "01:00" # dt_util.timedelta(hours=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_ENTITY_IDS): cv.entity_ids,
    vol.Optional(CONF_ROUND_DIGITS, default=2): vol.Coerce(int),
    vol.Optional(CONF_TIMESPAN, default=DEFAULT_TIMESPAN): cv.time_period
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the min/max/mean sensor."""
    entity_ids = config.get(CONF_ENTITY_IDS)
    name = config.get(CONF_NAME)
    round_digits = config.get(CONF_ROUND_DIGITS)
    timespan = config.get(CONF_TIMESPAN)

    async_add_entities(
        [ChangeSensor(hass, entity_ids, name, round_digits, timespan)],
        True)
    return True



def calc_delta(new_value, old_value):
    val = STATE_UNKNOWN
    if new_value != STATE_UNKNOWN:
        if old_value == STATE_UNKNOWN:
            val = abs(float(new_value))
        else:
          val = abs(float(new_value) - float(old_value))
    return val

def calc_accu_delta(new_delta, old_accu):
    val = STATE_UNKNOWN
    if new_delta != STATE_UNKNOWN:
        if old_accu == STATE_UNKNOWN:
            val = float(new_delta)
        else:
          val = float(old_accu) + float(delta)
    return val


class ChangeSensor(Entity):
    """Representation of a change sensor."""

    def __init__(self, hass, entity_ids, name, round_digits, timespan):
        """Initialize the change sensor."""
        self._hass = hass
        self._entity_ids = entity_ids
        self._round_digits = round_digits
        self._timespan = timespan

        if name:
            self._name = name
        else:
            self._name = '{} per {} hour sensor'.format('delta', timespan).capitalize()
        self._unit_of_measurement = None
        self._unit_of_measurement_mismatch = False
        self.delta = 0.0
        self.count_sensors = len(self._entity_ids)
        self.binary_sensor = -1
        self.updatestate = 0;

        if self.count_sensors == 2:
            if (self._entity_ids[0].split('.')[0] == 'binary_sensor'):
                self.binary_sensor = 0
            elif (self._entity_ids[1].split('.')[0] == 'binary_sensor'):
                self.binary_sensor = 1
            else:
                _LOGGER.warning(
                    "Too Many entity_ids, only the first entity with numeric values will be used",
                    self.count_sensors)

        if self.count_sensors > 2:
             _LOGGER.warning(
                    "Too Many entity_ids, only the first entity with numeric values will be used",
                    self.count_sensors)

        self.accu = STATE_UNKNOWN
        self.prev_value = STATE_UNKNOWN
        self.current_value = STATE_UNKNOWN
        self.last_state = STATE_UNKNOWN
        self.current_state = STATE_UNKNOWN
        self.last_update = dt_util.now().replace(microsecond=0,second=0,minute=0)


        @callback
        def async_change_sensor_state_listener_enable(entity, old_state, new_state):
            """Handle the sensor state changes."""
            if new_state.state is None or new_state.state in STATE_UNKNOWN:
                self.current_state = STATE_UNKNOWN
                hass.async_add_job(self.async_update_ha_state, True)
                return

            try:
                self.current_state = new_state.state

            except ValueError:
                _LOGGER.warning("Unable to store state. "
                                "Only numerical states are supported")

            hass.async_add_job(self.async_update_ha_state, True)

        @callback
        def async_change_sensor_state_listener(entity, old_state, new_state):
            if self._unit_of_measurement is None:
                self._unit_of_measurement = new_state.attributes.get(
                    ATTR_UNIT_OF_MEASUREMENT)

            try:
                self.current_value = float(new_state.state)
            except ValueError:
                _LOGGER.warning("Unable to store value "
                                "Only numerical states are supported")

            hass.async_add_job(self.async_update_ha_state, True)

        @callback
        def async_update_once(inputargs):
            self.updatestate = 1
            async_track_time_interval(
                self.hass, async_update_based_on_interval, self._timespan)

            hass.async_add_job(self.async_update_ha_state, True)

        @callback
        def async_update_based_on_interval(inputargs):
            self.updatestate = 1
            hass.async_add_job(self.async_update_ha_state, True)

        if self.count_sensors == 2 and self.binary_sensor >= 0:
            async_track_state_change(
                hass, entity_ids[self.binary_sensor], async_change_sensor_state_listener_enable)

            async_track_state_change(
                hass, entity_ids[self.binary_sensor - 1], async_change_sensor_state_listener)
        else:
            async_track_state_change(
                hass, entity_ids[0], async_change_sensor_state_listener)

        dtime = dt_util.now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        dtime = dtime+self._timespan
        if dtime.minute == 0:
            if dtime.hour == 0:
                first_update = dt_util.now().replace(microsecond=0,second=5,minute=0, hour=0)
                first_update = first_update + dt_util.dt.timedelta(days = 1)
                async_track_point_in_time(hass, async_update_once, first_update)

            else:
                first_update = dt_util.now().replace(microsecond=0,second=5,minute=0)
                first_update = first_update + dt_util.dt.timedelta(hours = 1)
                async_track_point_in_time(hass, async_update_once, first_update)

        else:
            first_update = dt_util.now().replace(microsecond=0,second=5)
            first_update = first_update + dt_util.dt.timedelta(minutes = 1)
            async_track_point_in_time(hass, async_update_once, first_update)



    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""

        return self.delta

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        if self._unit_of_measurement_mismatch:
            return "ERR"
        return self._unit_of_measurement

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def device_state_attributes(self):
        """Return the state attributes of the sensor."""
        state_attr = {
            attr: getattr(self, attr) for attr
            in ATTR_TO_PROPERTY if getattr(self, attr) is not None
        }
        return state_attr

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return ICON

    async def async_update(self):
        if self.prev_value == STATE_UNKNOWN and self.current_value != STATE_UNKNOWN:
            self.prev_value = self.current_value

        if self.last_state == STATE_UNKNOWN:
            self.last_state = False

        if self.updatestate == 0:
            """Update the accumulator and internal states """
            if self.binary_sensor >= 0:
                if self.current_state == False and self.last_state == True:
                    self.accu = calc_accu_delta(calc_delta(self.current_value, self.prev_value), self.accu)

                elif self.current_state == True and self.last_state == False:
                    self.prev_value = self.current_value

                self.last_state = self.current_state

        else:
            """Update the state at every interval"""
            if self.binary_sensor >= 0:
                if self.current_state == True:
                    self.delta = calc_accu_delta(calc_delta(self.current_value, self.prev_value), self.accu)

                elif self.current_state == False:
                    self.delta = self.accu

            else:
                self.delta = calc_delta(self.current_value, self.prev_value)

            self.prev_value = self.current_value
            self.last_update = dt_util.now()
            self.accu = 0.0
            self.updatestate = 0


