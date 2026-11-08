/* Android keyboard feedback through the attached SDL view. GPL-3.0-or-later. */
#include "extdll_menu.h"
#include "CzmMenu.h"

#ifdef __ANDROID__
#include <jni.h>
#include <dlfcn.h>

static JNIEnv *CzmHapticEnv( void )
{
	typedef void *( *GetEnvFn )( void );
	static GetEnvFn getEnv;
	static bool tried;
	if( !tried )
	{
		tried = true;
		void *sdl = dlopen( "libSDL2.so", RTLD_NOW | RTLD_NOLOAD );
		if( !sdl ) sdl = dlopen( "libSDL2.so", RTLD_NOW );
		if( sdl ) getEnv = (GetEnvFn)dlsym( sdl, "SDL_AndroidGetJNIEnv" );
	}
	return getEnv ? (JNIEnv *)getEnv() : NULL;
}
#endif

void CZM_MatchKeyHaptic( void )
{
#ifdef __ANDROID__
	JNIEnv *env = CzmHapticEnv();
	if( !env ) return;
	if( env->PushLocalFrame( 4 ) < 0 )
	{
		if( env->ExceptionCheck() ) env->ExceptionClear();
		return;
	}
	static jclass cls;
	static jmethodID method;
	if( !cls )
	{
		jclass local = env->FindClass( "ru/kurostreet/counterzombiemobile/CzmFeedback" );
		if( local && !env->ExceptionCheck() )
		{
			method = env->GetStaticMethodID( local, "matchKeyHaptic", "()V" );
			if( method && !env->ExceptionCheck() ) cls = (jclass)env->NewGlobalRef( local );
		}
	}
	if( cls && method && !env->ExceptionCheck() ) env->CallStaticVoidMethod( cls, method );
	if( env->ExceptionCheck() ) env->ExceptionClear();
	env->PopLocalFrame( NULL );
#endif
}
