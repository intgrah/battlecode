#include "cambc.h"
#include <stdio.h>

int main(void) {
    cambc_ctx* c = cambc_init();
    if (!c) return 1;
    while (1) {
        if (cambc_round(c) == 50) {
            cambc_resign(c, "c-nothing/50");
        }
        if (cambc_end_turn(c) < 0) break;
    }
    cambc_free(c);
    return 0;
}
