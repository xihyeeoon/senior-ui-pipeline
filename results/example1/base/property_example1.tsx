/**
 * v0 by Vercel.
 * @see https://v0.dev/t/0W13RkH
 * Documentation: https://v0.dev/docs#integrating-generated-code-into-your-nextjs-app
 */
export default function Component() {
    return (
      <section className="w-full py-12 md:py-24 lg:py-32 xl:py-48 bg-primary">
        <div className="container px-4 md:px-6">
          <div className="grid gap-6 items-center">
            <div className="flex flex-col justify-center space-y-8 text-center">
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tighter sm:text-5xl xl:text-6xl bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-500">
                  Discover Our Unique Features
                </h1>
                <p className="max-w-[600px] text-primary md:text-xl dark:text-primary-light mx-auto">
                  Our features are designed to enhance your productivity and streamline your workflow.
                </p>
              </div>
              <div className="w-full max-w-full space-y-4 mx-auto">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="flex flex-col items-center space-y-4 border-outline-variant p-6 rounded-lg">
                    <div className="p-2 bg-black bg-opacity-50 rounded-full">
                      <InboxIcon className="text-white h-6 w-6 mb-2 opacity-75" />
                    </div>
                    <h2 className="text-xl font-bold text-white">Smart Inbox</h2>
                    <p className="text-primary dark:text-primary-light">
                      Our Smart Inbox feature helps you manage your emails efficiently by prioritizing important emails.
                    </p>
                  </div>
                  <div className="flex flex-col items-center space-y-4 border-outline-variant p-6 rounded-lg">
                    <div className="p-2 bg-black bg-opacity-50 rounded-full">
                      <MergeIcon className="text-white h-6 w-6 mb-2 opacity-75" />
                    </div>
                    <h2 className="text-xl font-bold text-white">Seamless Integration</h2>
                    <p className="text-primary dark:text-primary-light">
                      Seamless Integration allows you to connect with your favorite apps and services without leaving your
                      inbox.
                    </p>
                  </div>
                  <div className="flex flex-col items-center space-y-4 border-outline-variant p-6 rounded-lg">
                    <div className="p-2 bg-black bg-opacity-50 rounded-full">
                      <SettingsIcon className="text-white h-6 w-6 mb-2 opacity-75" />
                    </div>
                    <h2 className="text-xl font-bold text-white">Advanced Customization</h2>
                    <p className="text-primary dark:text-primary-light">
                      With Advanced Customization, you can personalize your email client to suit your preferences and work
                      style.
                    </p>
                  </div>
                  <div className="flex flex-col items-center space-y-4 border-outline-variant p-6 rounded-lg">
                    <div className="p-2 bg-black bg-opacity-50 rounded-full">
                      <SearchIcon className="text-white h-6 w-6 mb-2 opacity-75" />
                    </div>
                    <h2 className="text-xl font-bold text-white">Powerful Search</h2>
                    <p className="text-primary dark:text-primary-light">
                      Our Powerful Search feature allows you to find any email, contact, or file in seconds.
                    </p>
                  </div>
                  <div className="flex flex-col items-center space-y-4 border-outline-variant p-6 rounded-lg">
                    <div className="p-2 bg-black bg-opacity-50 rounded-full">
                      <LockIcon className="text-white h-6 w-6 mb-2 opacity-75" />
                    </div>
                    <h2 className="text-xl font-bold text-white">Reliable Security</h2>
                    <p className="text-primary dark:text-primary-light">
                      With Reliable Security, your data is always safe and protected.
                    </p>
                  </div>
                  <div className="flex flex-col items-center space-y-4 border-outline-variant p-6 rounded-lg">
                    <div className="p-2 bg-black bg-opacity-50 rounded-full">
                      <MergeIcon className="text-white h-6 w-6 mb-2 opacity-75" />
                    </div>
                    <h2 className="text-xl font-bold text-white">Easy Collaboration</h2>
                    <p className="text-primary dark:text-primary-light">
                      Easy Collaboration allows you to share and edit documents with your team in real time.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    )
  }
  
  function InboxIcon(props) {
    return (
      <svg
        {...props}
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        <polyline points="18 10 14 10 12 12 8 12 6 10 2 10" />
        <path d="M4.45 4.11 2 10v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5l-2.45-5.89A2 2 0 0 0 14.76 3H5.24a2 2 0 0 0-1.79 1.11z" />
      </svg>
    )
  }
  
  
  function LockIcon(props) {
    return (
      <svg
        {...props}
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        <rect width="15" height="9" x="2.5" y="9" rx="2" ry="2" />
        <path d="M5.5 9V5a4 4 0 0 1 8 0v4" />
      </svg>
    )
  }
  
  
  function MergeIcon(props) {
    return (
      <svg
        {...props}
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        <path d="m7 5 3-3 3 3" />
        <path d="M10 2v8.3a3 3 0 0 1-.879 2.121L3 18" />
        <path d="m17 18-4-4" />
      </svg>
    )
  }
  
  
  function SearchIcon(props) {
    return (
      <svg
        {...props}
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        <circle cx="9" cy="9" r="7" />
        <path d="m18 18-3.3-3.3" />
      </svg>
    )
  }
  
  
  function SettingsIcon(props) {
    return (
      <svg
        {...props}
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        <path d="M10.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V18a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
        <circle cx="10" cy="10" r="3" />
      </svg>
    )
  }