idf_component_register(SRCS "cam_stream.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_wifi esp_http_server nvs_flash esp_event esp_netif log)
