/* Deliberate data race used to prove that the Linux TSan runner is active. */
#include <pthread.h>

static int shared_value;

static void *write_value(void *unused) {
    (void)unused;
    shared_value = 1;
    return NULL;
}

int main(void) {
    pthread_t thread;
    if (pthread_create(&thread, NULL, write_value, NULL) != 0) {
        return 2;
    }
    shared_value = 2;
    pthread_join(thread, NULL);
    return shared_value == 0;
}
