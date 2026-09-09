/* Deliberate data race used to prove that the Linux TSan runner is active. */
#include <pthread.h>

static volatile int shared_value;
static pthread_barrier_t start_barrier;

static void *write_value(void *unused) {
    (void)unused;
    (void)pthread_barrier_wait(&start_barrier);
    shared_value = 1;
    return NULL;
}

int main(void) {
    pthread_t thread;
    if (pthread_barrier_init(&start_barrier, NULL, 2) != 0) {
        return 3;
    }
    if (pthread_create(&thread, NULL, write_value, NULL) != 0) {
        (void)pthread_barrier_destroy(&start_barrier);
        return 2;
    }
    /* Both threads leave the barrier before either unsynchronised write. */
    (void)pthread_barrier_wait(&start_barrier);
    shared_value = 2;
    pthread_join(thread, NULL);
    (void)pthread_barrier_destroy(&start_barrier);
    return shared_value == 0;
}
