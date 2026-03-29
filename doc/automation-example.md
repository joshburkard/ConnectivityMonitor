# Automation Example

```yaml
automation:
  alias: "Connectivity Monitor - Device Alert"
  description: "Triggered by Connectivity Monitor. No trigger block needed."
  mode: parallel
  max: 10
  trigger: []
  action:
    - choose:
        - conditions:
            - condition: template
              value_template: "{{ recovered is defined and recovered }}"
          sequence:
            - service: notify.mobile_app_my_phone
              data:
                title: "✅ Device back online: {{ device_name }}"
                message: >-
                  {{ device_name }} ({{ device_address }}) is back online.
                  It was offline for
                  {% if hours_offline >= 1 %}
                    {{ hours_offline }} hour(s)
                  {% else %}
                    {{ minutes_offline }} minute(s)
                  {% endif %}
                  (down since {{ last_online }})
      default:
        - service: notify.mobile_app_my_phone
          data:
            title: "❌ Device offline: {{ device_name }}"
            message: >-
              {{ device_name }} ({{ device_address }}) has been offline for
              {% if hours_offline >= 1 %}
                {{ hours_offline }} hour(s)
              {% else %}
                {{ minutes_offline }} minute(s)
              {% endif %}
              (last seen: {{ last_online }})
```