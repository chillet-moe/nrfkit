/* SPDX-License-Identifier: BSD-3-Clause */
#define _GNU_SOURCE
#include <assert.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <runtime/nrfx/rram.c>

static mpsl_timeslot_callback_t handler;
static unsigned references, requests, closes;
static int open_error, request_error;
static bool initialized = true;
bool nrfkit_mpsl_is_initialized(void) {return initialized;}
int32_t nrfkit_mpsl_timeslot_retain(void) {++references; return 0;}
void nrfkit_mpsl_timeslot_release(void) {--references;}
void nrfkit_system_reset(void) {abort();}
int32_t mpsl_timeslot_session_open(mpsl_timeslot_callback_t cb,mpsl_timeslot_session_id_t *id) {
    handler=cb; *id=1; return open_error;
}
int32_t mpsl_timeslot_request(mpsl_timeslot_session_id_t id,const mpsl_timeslot_request_t *r) {
    assert(id==1); assert(r->params.earliest.length_us==600); ++requests; return request_error;
}
int32_t mpsl_timeslot_session_close(mpsl_timeslot_session_id_t id) {++closes; return 0;}
static void closed(void) {handler(1,MPSL_TIMESLOT_SIGNAL_SESSION_CLOSED); assert(references==0);}
int main(void) {
    void *memory=mmap((void *)0x100000,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    assert(memory==(void *)0x100000);
    struct nrfkit_rram_region region={0x100000,4096};
    uint32_t data[16]; for(unsigned i=0;i<16;++i) data[i]=i+1;
    assert(nrfkit_rram_submit(&region,0x100001,data,64)==-NRF_EINVAL);
    assert(nrfkit_rram_submit(&region,0x101000,data,16)==-NRF_EINVAL);
    struct nrfkit_rram_region forbidden={0xffd000,4096};
    assert(nrfkit_rram_submit(&forbidden,0xffd000,data,16)==-NRF_EINVAL);
    initialized=false; assert(nrfkit_rram_submit(&region,0x100000,data,64)==-NRF_EPERM); initialized=true;
    open_error=-NRF_ENOMEM; assert(nrfkit_rram_submit(&region,0x100000,data,64)==-NRF_ENOMEM); assert(references==0); open_error=0;
    fake_rram.CONFIG=17; fake_rram.POWER.CONFIG=23; fake_rram.READYNEXTTIMEOUT=31;
    assert(nrfkit_rram_submit(&region,0x100000,data,64)==0);
    assert(nrfkit_rram_submit(&region,0x100000,data,64)==-NRF_EAGAIN);
    nrfkit_rram_process(); assert(commits==0); assert(nrfkit_rram_result()==-NRF_EINPROGRESS);
    handler(1,MPSL_TIMESLOT_SIGNAL_BLOCKED); nrfkit_rram_process(); assert(requests==2);
    assert(request.params.earliest.priority==MPSL_TIMESLOT_PRIORITY_HIGH);
    for(unsigned i=0;i<4;++i) {
        assert(handler(1,MPSL_TIMESLOT_SIGNAL_START)->callback_action==MPSL_TIMESLOT_SIGNAL_ACTION_END);
        assert(commits==i+1);
        handler(1,MPSL_TIMESLOT_SIGNAL_SESSION_IDLE); nrfkit_rram_process();
    }
    assert(nrfkit_rram_result()==-NRF_EINPROGRESS); assert(closes==1); closed();
    assert(nrfkit_rram_result()==0); assert(memcmp(memory,data,64)==0);
    assert(fake_rram.CONFIG==17 && fake_rram.POWER.CONFIG==23 && fake_rram.READYNEXTTIMEOUT==31);
    assert(nrfkit_rram_submit(&region,0x100000,data,16)==0);
    fake_time+=TIMEOUT_US; nrfkit_rram_process(); closed();
    assert(nrfkit_rram_result()==-NRF_ETIMEDOUT);
    request_error=-NRF_EINVAL; assert(nrfkit_rram_submit(&region,0x100000,data,16)==0);
    nrfkit_rram_process(); nrfkit_rram_process(); closed(); assert(nrfkit_rram_result()==-NRF_EINVAL); request_error=0;
    corrupt_write=true; assert(nrfkit_rram_submit(&region,0x100000,data,16)==0);
    nrfkit_rram_process(); handler(1,MPSL_TIMESLOT_SIGNAL_START); handler(1,MPSL_TIMESLOT_SIGNAL_SESSION_IDLE);
    nrfkit_rram_process(); closed(); assert(nrfkit_rram_result()==-NRF_EIO);
    munmap(memory,4096);
}
