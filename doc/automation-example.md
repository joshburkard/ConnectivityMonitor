# Automation Example

```yaml
automation:
  alias: "Connectivity Monitor - Device Alert"
  mode: parallel
  max: 10
  trigger:
    - platform: event
      event_type: connectivity_monitor_alert
      # Optional: only react when this automation is the chosen action target:
      # event_data:
      #   action_entity_id: automation.connectivity_monitor_device_alert
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