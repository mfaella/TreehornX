struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_find(struct Node **root, int key) {
    struct Node *curr;
    int key_curr;
    curr = *root;
    while(curr != 0) {
        key_curr = curr->data;
        if (key_curr == key) {
            curr = 0;
        }
        else if (key < key_curr) {
            curr = curr->left;
            curr = curr->left;
        }
        else {
            curr = curr->right;
        }
    }
}

void bst_unsafe_insert(struct Node **root, int key) {
    struct Node *z;
    struct Node *x;
    struct Node *w;
    int xkey;
    int wkey;

    z = malloc(sizeof(struct Node));
    z->data = key;

    x = *root;

    if (x != 0) {//3
        xkey = x->data; //4
        if (xkey <= key) { //5
            w = x->right; //6
        }
        else {
            w = x->left; //7
        }
        while(w != 0) { //8
            wkey = w->data;
            x = w;
            if(wkey <= key) { //11
                w = w->right;
            }
            else {
                w = w->left; //13
            }
        }
        x = w; // 14 //error
        xkey = x->data; //15
        if (xkey <= key) {
            x->right = z;
        } 
        else {
            x->left = z;
        }
    }
}

void bst_remove_root_unsafe(struct Node **root) {
    struct Node *x;
    struct Node *ret;
    struct Node *xl;
    struct Node *xr;
    struct Node *rl;
    struct Node *rr;
    struct Node *par;
    struct Node *par_par;

    x = *root;
    if (x == 0) {
        ret = x;
    }
    else {
        xl = x->left;
        xr = x->right;
    
        if (xl == 0) {
            if (xr == 0) {
                free(x);
                ret = 0;
            } else {
                ret = xr;
                free(x);
            }
        } else {
            // Case: left child exists
            // (note: missing check for xr == NULL as per your comment)
            rl = xr->left;
            par = xr;
            par_par = x;
    
            while (rl != 0) {
                par_par = par;
                par = rl;
                rl = rl->left;
            }
    
            rr = par->right;
            par->left = xl;
    
            if (par_par == x) {
                free(x);
                ret = par;
            } else {
                par_par->left = rr;
                par->right = xr;
                free(x);
                ret = par;
            }
        }
    }
}
