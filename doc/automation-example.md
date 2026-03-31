# Automation Example

You can trigger an Automation on status change of the Overall sensor of a device. The Overall sensor can have this statuses:

- Connected
- Partially Connected
- Disconnected

To trigger automations, you have to create a Automation like this:

```yaml
automation:
  alias: "Connectivity Monitor - Device Alert"
  mode: parallel
  max: 10
  trigger:
    - platform: event
      event_type: connectivity_monitor_alert
  condition:
    - condition: template
      value_template: "{{ trigger.event.data.action_entity_id == this.entity_id }}"
  action:
    - choose:
        - conditions:
            - condition: template
              value_template: "{{ trigger.event.data.get('recovered', false) }}"
          sequence:
            - service: notify.mobile_app_my_phone
              data:
                title: "✅ {{ trigger.event.data.device_name }} is back online"
                message: >-
                  {{ trigger.event.data.device_name }}
                  ({{ trigger.event.data.device_address }}) recovered.
                  Was offline for
                  {% if trigger.event.data.hours_offline >= 1 %}
                    {{ trigger.event.data.hours_offline }} hr(s)
                  {% else %}
                    {{ trigger.event.data.minutes_offline }} min(s)
                  {% endif %}
                  — last seen: {{ trigger.event.data.last_online }}
      default:
        - service: notify.mobile_app_my_phone
          data:
            title: "❌ {{ trigger.event.data.device_name }} is offline"
            message: >-
              {{ trigger.event.data.device_name }}
              ({{ trigger.event.data.device_address }}) offline for
              {% if trigger.event.data.hours_offline >= 1 %}
                {{ trigger.event.data.hours_offline }} hr(s)
              {% else %}
                {{ trigger.event.data.minutes_offline }} min(s)
              {% endif %}
              — last seen: {{ trigger.event.data.last_online }}
```
