#include <wimf_c.h>

int main(void) {
    wimf_encode_options options;
    wimf_encode_options_init(&options);
    return wimf_abi_version() == WIMF_C_ABI_VERSION && options.quality == 7 ? 0 : 1;
}
